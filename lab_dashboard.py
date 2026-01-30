import streamlit as st
import requests
import json
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from functools import lru_cache
import time

# Page config
st.set_page_config(page_title="LAB Groep Dashboard", page_icon="📊", layout="wide")

# =============================================================================
# ODOO CONNECTION SETTINGS
# =============================================================================
ODOO_URL = "https://lab.odoo.works"
ODOO_DB = "bluezebra-works-nl-vestingh-production-13415483"
ODOO_USERNAME = "accounting@fidfinance.nl"

# Get API key from Streamlit secrets
try:
    ODOO_API_KEY = st.secrets["odoo_api_key"]
except Exception:
    ODOO_API_KEY = None

# Cache settings - 1 hour TTL for performance
CACHE_TTL = 3600

# =============================================================================
# COMPANY CONFIGURATION
# =============================================================================
COMPANIES = {
    1: "LAB Shops B.V.",
    2: "LAB Concept Store B.V.", 
    3: "LAB Vastgoed B.V.",
    5: "LAB Groep"
}

# Intercompany partner IDs for filtering
INTERCOMPANY_PARTNER_IDS = [1, 35, 51]  # LAB Shops, LAB Concept Store, LAB Vastgoed

# Account code mappings
# Revenue: 8xxx
# Costs: 4xxx (purchases), 6xxx (operating), 7xxx (COGS)
REVENUE_ACCOUNT_PREFIX = "8"
COST_ACCOUNT_PREFIXES = ["4", "6", "7"]

# =============================================================================
# SESSION STATE INITIALIZATION  
# =============================================================================
if 'cache_timestamp' not in st.session_state:
    st.session_state.cache_timestamp = time.time()

def clear_cache():
    """Clear all cached data by resetting timestamp"""
    st.session_state.cache_timestamp = time.time()
    st.cache_data.clear()

# =============================================================================
# ODOO API FUNCTIONS
# =============================================================================

def get_odoo_uid():
    """Authenticate and get user ID"""
    if not ODOO_API_KEY:
        return None
    
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "common",
            "method": "authenticate",
            "args": [ODOO_DB, ODOO_USERNAME, ODOO_API_KEY, {}]
        },
        "id": 1
    }
    
    try:
        response = requests.post(f"{ODOO_URL}/jsonrpc", json=payload, timeout=30)
        result = response.json()
        return result.get("result")
    except Exception as e:
        st.error(f"Authentication error: {e}")
        return None

@st.cache_data(ttl=CACHE_TTL)
def odoo_call(model, method, domain=None, fields=None, limit=None, _cache_key=None):
    """Generic Odoo API call with caching"""
    uid = get_odoo_uid()
    if not uid:
        return []
    
    args = [domain or []]
    kwargs = {}
    if fields:
        kwargs["fields"] = fields
    if limit:
        kwargs["limit"] = limit
    
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [ODOO_DB, uid, ODOO_API_KEY, model, method, args, kwargs]
        },
        "id": 2
    }
    
    try:
        response = requests.post(f"{ODOO_URL}/jsonrpc", json=payload, timeout=120)
        result = response.json()
        return result.get("result", [])
    except Exception as e:
        st.error(f"API error: {e}")
        return []

@st.cache_data(ttl=CACHE_TTL)
def odoo_read_group(model, domain, fields, groupby, _cache_key=None):
    """Odoo read_group for server-side aggregation - MUCH faster than search_read"""
    uid = get_odoo_uid()
    if not uid:
        return []
    
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [ODOO_DB, uid, ODOO_API_KEY, model, "read_group", 
                     [domain], 
                     {"fields": fields, "groupby": groupby, "lazy": False}]
        },
        "id": 3
    }
    
    try:
        response = requests.post(f"{ODOO_URL}/jsonrpc", json=payload, timeout=120)
        result = response.json()
        if "error" in result:
            st.error(f"read_group error: {result['error']}")
            return []
        return result.get("result", [])
    except Exception as e:
        st.error(f"API error in read_group: {e}")
        return []

# =============================================================================
# FAST DATA RETRIEVAL FUNCTIONS (using read_group)
# =============================================================================

def get_revenue_data_fast(company_id, year, use_intercompany_filter=False):
    """
    Get revenue data using read_group for server-side aggregation.
    Returns monthly totals instead of individual lines (~50x less data).
    
    Revenue accounts: 8xxx
    """
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    # Base domain for revenue
    domain = [
        ("company_id", "=", company_id),
        ("date", ">=", start_date),
        ("date", "<=", end_date),
        ("parent_state", "=", "posted"),
        ("account_id.code", "=like", "8%")
    ]
    
    # If intercompany filter is ON, we need legacy method for partner filtering
    if use_intercompany_filter:
        return get_revenue_data_legacy(company_id, year, exclude_intercompany=True)
    
    # Use read_group for fast server-side aggregation
    result = odoo_read_group(
        "account.move.line",
        domain,
        ["balance:sum"],
        ["date:month"],
        _cache_key=f"revenue_fast_{company_id}_{year}_{st.session_state.cache_timestamp}"
    )
    
    # Parse results into monthly data
    monthly_data = {}
    total = 0
    
    for group in result:
        # date:month returns format like "January 2025" or "januari 2025"
        month_str = group.get("date:month", "")
        balance = group.get("balance", 0) or 0
        
        # Revenue is negative in Odoo (credit), so we invert
        revenue = -balance
        total += revenue
        
        # Extract month number from the string
        month_num = extract_month_number(month_str, year)
        if month_num:
            monthly_data[month_num] = revenue
    
    return {"total": total, "monthly": monthly_data}

def get_cost_data_fast(company_id, year, use_intercompany_filter=False):
    """
    Get cost data using read_group for server-side aggregation.
    Returns monthly totals instead of individual lines (~50x less data).
    
    Cost accounts: 4xxx, 6xxx, 7xxx
    """
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    # If intercompany filter is ON, we need legacy method for partner filtering
    if use_intercompany_filter:
        return get_cost_data_legacy(company_id, year, exclude_intercompany=True)
    
    # Build domain with OR for multiple account prefixes
    # Cost accounts: 4xxx (purchases), 6xxx (operating), 7xxx (COGS)
    domain = [
        ("company_id", "=", company_id),
        ("date", ">=", start_date),
        ("date", "<=", end_date),
        ("parent_state", "=", "posted"),
        "|", "|",
        ("account_id.code", "=like", "4%"),
        ("account_id.code", "=like", "6%"),
        ("account_id.code", "=like", "7%")
    ]
    
    # Use read_group for fast server-side aggregation
    result = odoo_read_group(
        "account.move.line",
        domain,
        ["balance:sum"],
        ["date:month"],
        _cache_key=f"cost_fast_{company_id}_{year}_{st.session_state.cache_timestamp}"
    )
    
    # Parse results into monthly data
    monthly_data = {}
    total = 0
    
    for group in result:
        month_str = group.get("date:month", "")
        balance = group.get("balance", 0) or 0
        
        # Costs are positive in Odoo (debit)
        cost = balance
        total += cost
        
        month_num = extract_month_number(month_str, year)
        if month_num:
            monthly_data[month_num] = cost
    
    return {"total": total, "monthly": monthly_data}

def extract_month_number(month_str, year):
    """
    Extract month number from Odoo's date:month grouping string.
    Handles multiple languages (English, Dutch, etc.)
    """
    if not month_str:
        return None
    
    month_str_lower = month_str.lower()
    
    # Month mappings (English and Dutch)
    month_map = {
        "january": 1, "januari": 1, "jan": 1,
        "february": 2, "februari": 2, "feb": 2,
        "march": 3, "maart": 3, "mar": 3, "mrt": 3,
        "april": 4, "apr": 4,
        "may": 5, "mei": 5,
        "june": 6, "juni": 6, "jun": 6,
        "july": 7, "juli": 7, "jul": 7,
        "august": 8, "augustus": 8, "aug": 8,
        "september": 9, "sep": 9, "sept": 9,
        "october": 10, "oktober": 10, "oct": 10, "okt": 10,
        "november": 11, "nov": 11,
        "december": 12, "dec": 12
    }
    
    for month_name, month_num in month_map.items():
        if month_name in month_str_lower:
            return month_num
    
    return None

# =============================================================================
# LEGACY DATA RETRIEVAL (for intercompany filtering)
# =============================================================================

@st.cache_data(ttl=CACHE_TTL)
def get_revenue_data_legacy(company_id, year, exclude_intercompany=False, _cache_key=None):
    """Legacy method - fetches individual lines (slower but supports IC filtering)"""
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    domain = [
        ("company_id", "=", company_id),
        ("date", ">=", start_date),
        ("date", "<=", end_date),
        ("parent_state", "=", "posted"),
        ("account_id.code", "=like", "8%")
    ]
    
    if exclude_intercompany:
        domain.append(("partner_id", "not in", INTERCOMPANY_PARTNER_IDS))
    
    data = odoo_call(
        "account.move.line",
        "search_read",
        domain,
        ["balance", "date", "partner_id"],
        limit=100000,
        _cache_key=f"revenue_legacy_{company_id}_{year}_{exclude_intercompany}_{st.session_state.cache_timestamp}"
    )
    
    monthly_data = {}
    total = 0
    
    for line in data:
        balance = line.get("balance", 0) or 0
        revenue = -balance  # Revenue is credit (negative)
        total += revenue
        
        date_str = line.get("date", "")
        if date_str:
            month = int(date_str.split("-")[1])
            monthly_data[month] = monthly_data.get(month, 0) + revenue
    
    return {"total": total, "monthly": monthly_data}

@st.cache_data(ttl=CACHE_TTL)
def get_cost_data_legacy(company_id, year, exclude_intercompany=False, _cache_key=None):
    """Legacy method - fetches individual lines (slower but supports IC filtering)"""
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    # Cost accounts: 4xxx, 6xxx, 7xxx (NOT 8xxx - that's revenue)
    domain = [
        ("company_id", "=", company_id),
        ("date", ">=", start_date),
        ("date", "<=", end_date),
        ("parent_state", "=", "posted"),
        "|", "|",
        ("account_id.code", "=like", "4%"),
        ("account_id.code", "=like", "6%"),
        ("account_id.code", "=like", "7%")
    ]
    
    if exclude_intercompany:
        domain.append(("partner_id", "not in", INTERCOMPANY_PARTNER_IDS))
    
    data = odoo_call(
        "account.move.line",
        "search_read",
        domain,
        ["balance", "date", "partner_id"],
        limit=100000,
        _cache_key=f"cost_legacy_{company_id}_{year}_{exclude_intercompany}_{st.session_state.cache_timestamp}"
    )
    
    monthly_data = {}
    total = 0
    
    for line in data:
        balance = line.get("balance", 0) or 0
        total += balance  # Costs are debit (positive)
        
        date_str = line.get("date", "")
        if date_str:
            month = int(date_str.split("-")[1])
            monthly_data[month] = monthly_data.get(month, 0) + balance
    
    return {"total": total, "monthly": monthly_data}

# =============================================================================
# COMBINED DATA FUNCTION
# =============================================================================

def get_revenue_vs_cost_fast(company_id, year, use_intercompany_filter=False):
    """
    Get both revenue and cost data efficiently.
    Uses read_group when possible, falls back to legacy for IC filtering.
    """
    with st.spinner(f"Omzet laden..."):
        revenue_data = get_revenue_data_fast(company_id, year, use_intercompany_filter)
    
    with st.spinner(f"Kosten laden..."):
        cost_data = get_cost_data_fast(company_id, year, use_intercompany_filter)
    
    return {
        "revenue": revenue_data,
        "costs": cost_data,
        "profit": revenue_data["total"] - cost_data["total"]
    }

# =============================================================================
# BANK BALANCE FUNCTION
# =============================================================================

@st.cache_data(ttl=CACHE_TTL)
def get_bank_balance(company_id, _cache_key=None):
    """Get current bank balance for a company (account 1100)"""
    domain = [
        ("company_id", "=", company_id),
        ("account_id.code", "=like", "1100%"),
        ("parent_state", "=", "posted")
    ]
    
    result = odoo_read_group(
        "account.move.line",
        domain,
        ["balance:sum"],
        [],
        _cache_key=f"bank_{company_id}_{st.session_state.cache_timestamp}"
    )
    
    if result and len(result) > 0:
        return result[0].get("balance", 0) or 0
    return 0

# =============================================================================
# FORMATTING HELPERS
# =============================================================================

def format_currency(amount):
    """Format amount as Euro currency"""
    if amount is None:
        return "€ 0"
    return f"€ {amount:,.0f}".replace(",", ".")

def format_percentage(value):
    """Format as percentage"""
    if value is None:
        return "0%"
    return f"{value:.1f}%"

# =============================================================================
# DASHBOARD UI
# =============================================================================

def main():
    st.title("📊 LAB Groep Dashboard")
    
    # Check API key
    if not ODOO_API_KEY:
        st.error("⚠️ Odoo API key niet geconfigureerd. Voeg 'odoo_api_key' toe aan Streamlit Secrets.")
        st.stop()
    
    # Sidebar
    st.sidebar.title("⚙️ Instellingen")
    
    # Company selector
    company_options = {v: k for k, v in COMPANIES.items()}
    selected_company_name = st.sidebar.selectbox(
        "Bedrijf",
        options=list(COMPANIES.values()),
        index=0
    )
    selected_company_id = company_options[selected_company_name]
    
    # Year selector
    current_year = datetime.now().year
    years = list(range(current_year, 2019, -1))
    selected_year = st.sidebar.selectbox("Jaar", options=years, index=0)
    
    # Intercompany filter
    exclude_intercompany = st.sidebar.checkbox(
        "🔄 Intercompany uitsluiten",
        value=False,
        help="Sluit transacties tussen LAB entiteiten uit"
    )
    
    # Refresh button
    if st.sidebar.button("🔄 Ververs Data"):
        clear_cache()
        st.rerun()
    
    # Show cache status
    cache_age = time.time() - st.session_state.cache_timestamp
    if cache_age < 60:
        cache_str = f"{int(cache_age)} sec"
    else:
        cache_str = f"{int(cache_age/60)} min"
    st.sidebar.caption(f"Cache: {cache_str} oud")
    
    # =============================================================================
    # MAIN CONTENT - TABS
    # =============================================================================
    
    tab_overview, tab_details, tab_trends = st.tabs(["📈 Overzicht", "📋 Details", "📊 Trends"])
    
    # =========================================================================
    # TAB 1: OVERVIEW
    # =========================================================================
    with tab_overview:
        st.header(f"{selected_company_name} - {selected_year}")
        
        # Get data
        data = get_revenue_vs_cost_fast(selected_company_id, selected_year, exclude_intercompany)
        
        # KPI Cards
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "💰 Omzet",
                format_currency(data["revenue"]["total"]),
                help="Totale omzet (8xxx rekeningen)"
            )
        
        with col2:
            st.metric(
                "📉 Kosten",
                format_currency(data["costs"]["total"]),
                help="Totale kosten (4xxx, 6xxx, 7xxx rekeningen)"
            )
        
        with col3:
            profit = data["profit"]
            st.metric(
                "📊 Resultaat",
                format_currency(profit),
                delta=format_currency(profit) if profit != 0 else None,
                delta_color="normal" if profit >= 0 else "inverse"
            )
        
        with col4:
            margin = (profit / data["revenue"]["total"] * 100) if data["revenue"]["total"] != 0 else 0
            st.metric(
                "📏 Marge",
                format_percentage(margin),
                help="Winstmarge (Resultaat / Omzet)"
            )
        
        # Monthly chart
        st.subheader("📅 Maandoverzicht")
        
        months = ["Jan", "Feb", "Mrt", "Apr", "Mei", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dec"]
        revenue_monthly = [data["revenue"]["monthly"].get(i, 0) for i in range(1, 13)]
        cost_monthly = [data["costs"]["monthly"].get(i, 0) for i in range(1, 13)]
        profit_monthly = [r - c for r, c in zip(revenue_monthly, cost_monthly)]
        
        fig = go.Figure()
        fig.add_trace(go.Bar(name="Omzet", x=months, y=revenue_monthly, marker_color="#2ecc71"))
        fig.add_trace(go.Bar(name="Kosten", x=months, y=cost_monthly, marker_color="#e74c3c"))
        fig.add_trace(go.Scatter(name="Resultaat", x=months, y=profit_monthly, mode="lines+markers", line=dict(color="#3498db", width=3)))
        
        fig.update_layout(
            barmode="group",
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis_title="Bedrag (€)",
            xaxis_title="Maand"
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Bank balance
        st.subheader("🏦 Bankstand")
        bank_balance = get_bank_balance(selected_company_id, _cache_key=f"bank_{st.session_state.cache_timestamp}")
        st.metric("Huidige Bankstand", format_currency(bank_balance))
    
    # =========================================================================
    # TAB 2: DETAILS
    # =========================================================================
    with tab_details:
        st.header("📋 Details")
        
        # Monthly breakdown table
        st.subheader("Maandelijkse Uitsplitsing")
        
        table_data = []
        for i, month in enumerate(months, 1):
            rev = data["revenue"]["monthly"].get(i, 0)
            cost = data["costs"]["monthly"].get(i, 0)
            profit = rev - cost
            margin = (profit / rev * 100) if rev != 0 else 0
            
            table_data.append({
                "Maand": month,
                "Omzet": format_currency(rev),
                "Kosten": format_currency(cost),
                "Resultaat": format_currency(profit),
                "Marge": format_percentage(margin)
            })
        
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Download button
        csv = df.to_csv(index=False)
        st.download_button(
            "📥 Download CSV",
            csv,
            f"{selected_company_name}_{selected_year}_overzicht.csv",
            "text/csv"
        )
    
    # =========================================================================
    # TAB 3: TRENDS
    # =========================================================================
    with tab_trends:
        st.header("📊 Trends")
        
        # Multi-year comparison
        st.subheader("Jaarlijkse Vergelijking")
        
        years_to_compare = [selected_year, selected_year - 1, selected_year - 2]
        comparison_data = []
        
        for year in years_to_compare:
            year_data = get_revenue_vs_cost_fast(selected_company_id, year, exclude_intercompany)
            comparison_data.append({
                "Jaar": str(year),
                "Omzet": year_data["revenue"]["total"],
                "Kosten": year_data["costs"]["total"],
                "Resultaat": year_data["profit"]
            })
        
        df_comparison = pd.DataFrame(comparison_data)
        
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(name="Omzet", x=df_comparison["Jaar"], y=df_comparison["Omzet"], marker_color="#2ecc71"))
        fig2.add_trace(go.Bar(name="Kosten", x=df_comparison["Jaar"], y=df_comparison["Kosten"], marker_color="#e74c3c"))
        fig2.add_trace(go.Bar(name="Resultaat", x=df_comparison["Jaar"], y=df_comparison["Resultaat"], marker_color="#3498db"))
        
        fig2.update_layout(
            barmode="group",
            height=400,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            yaxis_title="Bedrag (€)"
        )
        
        st.plotly_chart(fig2, use_container_width=True)
        
        # YoY Growth
        st.subheader("📈 Groei jaar-op-jaar")
        
        if len(comparison_data) >= 2:
            current = comparison_data[0]
            previous = comparison_data[1]
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if previous["Omzet"] != 0:
                    growth = ((current["Omzet"] - previous["Omzet"]) / previous["Omzet"]) * 100
                    st.metric("Omzet Groei", format_percentage(growth), delta=format_percentage(growth))
                else:
                    st.metric("Omzet Groei", "N/A")
            
            with col2:
                if previous["Kosten"] != 0:
                    growth = ((current["Kosten"] - previous["Kosten"]) / previous["Kosten"]) * 100
                    st.metric("Kosten Groei", format_percentage(growth), delta=format_percentage(growth), delta_color="inverse")
                else:
                    st.metric("Kosten Groei", "N/A")
            
            with col3:
                if previous["Resultaat"] != 0:
                    growth = ((current["Resultaat"] - previous["Resultaat"]) / abs(previous["Resultaat"])) * 100
                    st.metric("Resultaat Groei", format_percentage(growth), delta=format_percentage(growth))
                else:
                    st.metric("Resultaat Groei", "N/A")

if __name__ == "__main__":
    main()
