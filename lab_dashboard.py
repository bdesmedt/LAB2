"""
LAB Groep Financial Dashboard v9 OPTIMIZED
==========================================
Server-side aggregation for 10x faster load times

Optimizations:
- read_group() for revenue/cost data (Odoo aggregates instead of fetching 100K records)
- Cache TTL extended from 5 min to 1 hour
- Smart fallback: read_group when IC filter OFF, legacy when IC filter ON

Expected performance:
- Overview tab: ~3 sec (was ~30 sec)
- 2025 data: Should load completely now
"""
import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime, timedelta
import calendar

# Try to import plotly, install if needed
try:
    import plotly.express as px
    import plotly.graph_objects as go
except ImportError:
    import subprocess
    subprocess.check_call(["pip", "install", "plotly"])
    import plotly.express as px
    import plotly.graph_objects as go

# =================================================================
# CONFIGURATION
# =================================================================
CACHE_TTL = 3600  # 1 hour cache (was 300 seconds / 5 min)
RECORD_LIMIT = 100000  # Max records to fetch (fallback mode)

# Odoo connection settings
ODOO_URL = "https://lab.odoo.works"
ODOO_DB = "bluezebra-works-nl-vestingh-production-13415483"
ODOO_USER = "accounting@fidfinance.nl"

# Company IDs
COMPANIES = {
    1: "LAB Shops B.V.",
    3: "LAB Conceptstore B.V.", 
    4: "LAB Projects B.V."
}

# Revenue account codes (70xxxx)
REVENUE_ACCOUNTS = ['700000', '700010', '700015', '700020', '700100', '700105', '700110', '700200', '703000', '704000', '705000', '706000', '707000', '708000', '708001', '709000']

# Intercompany partner IDs for filtering
INTERCOMPANY_PARTNER_IDS = [1, 37, 38]  # LAB Shops, LAB Conceptstore, LAB Projects

# =================================================================
# DUTCH TRANSLATIONS
# =================================================================
MONTH_NAMES_NL = {
    1: 'Januari', 2: 'Februari', 3: 'Maart', 4: 'April',
    5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Augustus',
    9: 'September', 10: 'Oktober', 11: 'November', 12: 'December'
}

MONTH_ABBREV_NL = {
    1: 'Jan', 2: 'Feb', 3: 'Mrt', 4: 'Apr',
    5: 'Mei', 6: 'Jun', 7: 'Jul', 8: 'Aug',
    9: 'Sep', 10: 'Okt', 11: 'Nov', 12: 'Dec'
}

# English month name to number mapping (for read_group results)
MONTH_EN_TO_NUM = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12
}

# =================================================================
# ODOO API CONNECTION
# =================================================================

def get_api_key():
    """Get API key from Streamlit secrets or session state"""
    # First check secrets
    if hasattr(st, 'secrets') and 'ODOO_API_KEY' in st.secrets:
        return st.secrets['ODOO_API_KEY']
    # Then check session state
    if 'odoo_api_key' in st.session_state and st.session_state.odoo_api_key:
        return st.session_state.odoo_api_key
    return None

def get_uid():
    """Get UID from secrets or use default"""
    if hasattr(st, 'secrets') and 'ODOO_UID' in st.secrets:
        return st.secrets['ODOO_UID']
    return 37  # Default UID

def odoo_call(model, method, domain=None, fields=None, limit=None, offset=0, order=None, groupby=None, context=None):
    """Make Odoo JSON-RPC call with improved error handling"""
    api_key = get_api_key()
    if not api_key:
        return None
    
    uid = get_uid()
    
    # Build args based on method
    if method == "search_read":
        args = [domain or []]
        kwargs = {"fields": fields or [], "limit": limit, "offset": offset}
        if order:
            kwargs["order"] = order
    elif method == "read_group":
        args = [domain or [], fields or [], groupby or []]
        kwargs = {"lazy": False}
    elif method == "search_count":
        args = [domain or []]
        kwargs = {}
    else:
        args = [domain or []]
        kwargs = {}
    
    if context:
        kwargs["context"] = context
    
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [ODOO_DB, uid, api_key, model, method, args, kwargs]
        },
        "id": 1
    }
    
    try:
        response = requests.post(
            f"{ODOO_URL}/jsonrpc",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=120  # Increased timeout for large queries
        )
        result = response.json()
        if "error" in result:
            error_msg = result["error"].get("data", {}).get("message", str(result["error"]))
            st.error(f"Odoo API Error: {error_msg}")
            return None
        return result.get("result")
    except requests.exceptions.Timeout:
        st.error("⏱️ Timeout bij ophalen data. Probeer een kleinere dataset.")
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Connection error: {str(e)}")
        return None
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")
        return None

# =================================================================
# OPTIMIZED DATA FUNCTIONS (using read_group)
# =================================================================

def parse_month_from_group(date_str):
    """Parse month number from Odoo read_group date string like 'January 2025'"""
    if not date_str:
        return None
    parts = date_str.lower().split()
    if len(parts) >= 1:
        month_name = parts[0]
        return MONTH_EN_TO_NUM.get(month_name)
    return None

@st.cache_data(ttl=CACHE_TTL)
def get_revenue_data_fast(year, company_id=None):
    """
    OPTIMIZED: Get revenue data using read_group for server-side aggregation.
    Returns dict with monthly totals instead of individual records.
    """
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    domain = [
        ("date", ">=", start_date),
        ("date", "<=", end_date),
        ("account_id.code", "=like", "7%"),
        ("parent_state", "=", "posted")
    ]
    
    if company_id:
        domain.append(("company_id", "=", company_id))
    
    # Use read_group for server-side aggregation
    result = odoo_call(
        "account.move.line",
        "read_group",
        domain=domain,
        fields=["balance:sum"],
        groupby=["date:month", "company_id"]
    )
    
    if not result:
        return None
    
    # Convert to monthly totals
    monthly_data = {}
    for item in result:
        month = parse_month_from_group(item.get('date:month'))
        comp_id = item.get('company_id')[0] if item.get('company_id') else None
        balance = item.get('balance', 0) or 0
        
        if month:
            key = (month, comp_id)
            monthly_data[key] = monthly_data.get(key, 0) + balance
    
    return monthly_data

@st.cache_data(ttl=CACHE_TTL)
def get_cost_data_fast(year, company_id=None):
    """
    OPTIMIZED: Get cost data using read_group for server-side aggregation.
    Cost accounts: 4xxxxx, 6xxxxx, 8xxxxx
    """
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    # We need to query each account range separately due to Odoo domain limitations
    monthly_data = {}
    
    for prefix in ['4', '6', '8']:
        domain = [
            ("date", ">=", start_date),
            ("date", "<=", end_date),
            ("account_id.code", "=like", f"{prefix}%"),
            ("parent_state", "=", "posted")
        ]
        
        if company_id:
            domain.append(("company_id", "=", company_id))
        
        result = odoo_call(
            "account.move.line",
            "read_group",
            domain=domain,
            fields=["balance:sum"],
            groupby=["date:month", "company_id"]
        )
        
        if result:
            for item in result:
                month = parse_month_from_group(item.get('date:month'))
                comp_id = item.get('company_id')[0] if item.get('company_id') else None
                balance = item.get('balance', 0) or 0
                
                if month:
                    key = (month, comp_id)
                    monthly_data[key] = monthly_data.get(key, 0) + balance
    
    return monthly_data

@st.cache_data(ttl=CACHE_TTL)
def get_revenue_vs_cost_fast(year, company_id=None):
    """
    OPTIMIZED: Get both revenue and cost in efficient format for charting.
    Returns DataFrame with Month, Revenue, Cost, Profit columns.
    """
    revenue_data = get_revenue_data_fast(year, company_id)
    cost_data = get_cost_data_fast(year, company_id)
    
    if revenue_data is None and cost_data is None:
        return None
    
    # Build monthly summary
    rows = []
    for month in range(1, 13):
        # Sum across all companies if no specific company selected
        if company_id:
            rev = revenue_data.get((month, company_id), 0) if revenue_data else 0
            cost = cost_data.get((month, company_id), 0) if cost_data else 0
        else:
            rev = sum(v for (m, c), v in (revenue_data or {}).items() if m == month)
            cost = sum(v for (m, c), v in (cost_data or {}).items() if m == month)
        
        # Revenue is negative in Odoo (credit), costs are positive (debit)
        revenue = -rev
        costs = cost
        
        rows.append({
            'Maand': MONTH_ABBREV_NL[month],
            'Maand_Num': month,
            'Omzet': revenue,
            'Kosten': costs,
            'Winst': revenue - costs
        })
    
    return pd.DataFrame(rows)

# =================================================================
# LEGACY DATA FUNCTIONS (for detailed analysis and IC filtering)
# =================================================================

@st.cache_data(ttl=CACHE_TTL)
def get_revenue_data(year, company_id=None):
    """Get revenue data (account codes starting with 7) - LEGACY for detailed analysis"""
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    domain = [
        ("date", ">=", start_date),
        ("date", "<=", end_date),
        ("account_id.code", "=like", "7%"),
        ("parent_state", "=", "posted")
    ]
    
    if company_id:
        domain.append(("company_id", "=", company_id))
    
    fields = ["date", "balance", "company_id", "account_id", "partner_id", "name", "move_id"]
    
    data = odoo_call("account.move.line", "search_read", domain, fields, limit=RECORD_LIMIT)
    return data

@st.cache_data(ttl=CACHE_TTL)
def get_cost_data(year, company_id=None):
    """Get cost data (accounts 4x, 6x, 8x) - LEGACY for detailed analysis"""
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    all_data = []
    
    for prefix in ['4', '6', '8']:
        domain = [
            ("date", ">=", start_date),
            ("date", "<=", end_date),
            ("account_id.code", "=like", f"{prefix}%"),
            ("parent_state", "=", "posted")
        ]
        
        if company_id:
            domain.append(("company_id", "=", company_id))
        
        fields = ["date", "balance", "company_id", "account_id", "partner_id", "name", "move_id"]
        
        data = odoo_call("account.move.line", "search_read", domain, fields, limit=RECORD_LIMIT)
        if data:
            all_data.extend(data)
    
    return all_data

@st.cache_data(ttl=CACHE_TTL)
def get_top_customers(year, company_id=None, limit=10):
    """Get top customers by revenue"""
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    domain = [
        ("date", ">=", start_date),
        ("date", "<=", end_date),
        ("account_id.code", "=like", "7%"),
        ("parent_state", "=", "posted"),
        ("partner_id", "!=", False)
    ]
    
    if company_id:
        domain.append(("company_id", "=", company_id))
    
    fields = ["partner_id", "balance"]
    
    data = odoo_call("account.move.line", "search_read", domain, fields, limit=RECORD_LIMIT)
    
    if not data:
        return None
    
    # Aggregate by partner
    partner_totals = {}
    for record in data:
        partner = record.get('partner_id')
        if partner:
            partner_id = partner[0]
            partner_name = partner[1]
            balance = record.get('balance', 0) or 0
            
            if partner_id not in partner_totals:
                partner_totals[partner_id] = {'name': partner_name, 'total': 0}
            partner_totals[partner_id]['total'] += balance
    
    # Sort by revenue (most negative = most revenue)
    sorted_partners = sorted(partner_totals.items(), key=lambda x: x[1]['total'])
    
    # Take top N
    top = sorted_partners[:limit]
    
    return [{'partner_id': p[0], 'name': p[1]['name'], 'revenue': -p[1]['total']} for p in top]

@st.cache_data(ttl=CACHE_TTL)
def get_top_suppliers(year, company_id=None, limit=10):
    """Get top suppliers by cost"""
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    all_data = []
    
    for prefix in ['4', '6']:
        domain = [
            ("date", ">=", start_date),
            ("date", "<=", end_date),
            ("account_id.code", "=like", f"{prefix}%"),
            ("parent_state", "=", "posted"),
            ("partner_id", "!=", False)
        ]
        
        if company_id:
            domain.append(("company_id", "=", company_id))
        
        fields = ["partner_id", "balance"]
        
        data = odoo_call("account.move.line", "search_read", domain, fields, limit=RECORD_LIMIT)
        if data:
            all_data.extend(data)
    
    if not all_data:
        return None
    
    # Aggregate by partner
    partner_totals = {}
    for record in all_data:
        partner = record.get('partner_id')
        if partner:
            partner_id = partner[0]
            partner_name = partner[1]
            balance = record.get('balance', 0) or 0
            
            if partner_id not in partner_totals:
                partner_totals[partner_id] = {'name': partner_name, 'total': 0}
            partner_totals[partner_id]['total'] += balance
    
    # Sort by cost (most positive = most cost)
    sorted_partners = sorted(partner_totals.items(), key=lambda x: x[1]['total'], reverse=True)
    
    # Take top N
    top = sorted_partners[:limit]
    
    return [{'partner_id': p[0], 'name': p[1]['name'], 'cost': p[1]['total']} for p in top]

@st.cache_data(ttl=CACHE_TTL)
def get_receivables_payables(company_id=None):
    """Get current receivables (12xxxx, 14xxxx) and payables (16xxxx)"""
    # Receivables: 12xxxx (Debiteuren) and 14xxxx (Overige vorderingen)
    receivable_domain = [
        ("account_id.code", "=like", "12%"),
        ("parent_state", "=", "posted")
    ]
    
    other_receivable_domain = [
        ("account_id.code", "=like", "14%"),
        ("parent_state", "=", "posted")
    ]
    
    # Payables: 16xxxx (Crediteuren)
    payable_domain = [
        ("account_id.code", "=like", "16%"),
        ("parent_state", "=", "posted")
    ]
    
    if company_id:
        receivable_domain.append(("company_id", "=", company_id))
        other_receivable_domain.append(("company_id", "=", company_id))
        payable_domain.append(("company_id", "=", company_id))
    
    fields = ["balance", "company_id"]
    
    receivables = odoo_call("account.move.line", "search_read", receivable_domain, fields, limit=RECORD_LIMIT)
    other_receivables = odoo_call("account.move.line", "search_read", other_receivable_domain, fields, limit=RECORD_LIMIT)
    payables = odoo_call("account.move.line", "search_read", payable_domain, fields, limit=RECORD_LIMIT)
    
    total_receivables = sum(r.get('balance', 0) or 0 for r in (receivables or []))
    total_other_receivables = sum(r.get('balance', 0) or 0 for r in (other_receivables or []))
    total_payables = sum(r.get('balance', 0) or 0 for r in (payables or []))
    
    return {
        'receivables': total_receivables + total_other_receivables,
        'payables': -total_payables  # Make positive for display
    }

@st.cache_data(ttl=CACHE_TTL)
def get_product_sales(year, company_id=None):
    """Get product sales data for analysis"""
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    domain = [
        ("date", ">=", start_date),
        ("date", "<=", end_date),
        ("account_id.code", "=like", "7%"),
        ("parent_state", "=", "posted"),
        ("product_id", "!=", False)
    ]
    
    if company_id:
        domain.append(("company_id", "=", company_id))
    
    fields = ["product_id", "balance", "quantity", "company_id"]
    
    data = odoo_call("account.move.line", "search_read", domain, fields, limit=RECORD_LIMIT)
    return data

@st.cache_data(ttl=CACHE_TTL)
def get_pos_orders(year, company_id=None):
    """Get POS order data for LAB Conceptstore analysis"""
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    domain = [
        ("date_order", ">=", start_date),
        ("date_order", "<=", end_date),
        ("state", "in", ["paid", "done", "invoiced"])
    ]
    
    if company_id:
        domain.append(("company_id", "=", company_id))
    
    fields = ["name", "date_order", "amount_total", "amount_tax", "partner_id", 
              "company_id", "pos_reference", "state", "lines"]
    
    data = odoo_call("pos.order", "search_read", domain, fields, limit=RECORD_LIMIT)
    return data

@st.cache_data(ttl=CACHE_TTL)
def get_pos_order_lines(order_ids):
    """Get POS order lines for specific orders"""
    if not order_ids:
        return []
    
    domain = [("order_id", "in", order_ids)]
    fields = ["order_id", "product_id", "qty", "price_subtotal", "price_subtotal_incl", "discount"]
    
    data = odoo_call("pos.order.line", "search_read", domain, fields, limit=RECORD_LIMIT)
    return data

@st.cache_data(ttl=CACHE_TTL)
def get_product_categories():
    """Get all product categories"""
    fields = ["id", "name", "complete_name", "parent_id"]
    data = odoo_call("product.category", "search_read", [], fields, limit=1000)
    return {c['id']: c for c in (data or [])}

@st.cache_data(ttl=CACHE_TTL)
def get_product_info(product_ids):
    """Get product information for given IDs"""
    if not product_ids:
        return {}
    
    domain = [("id", "in", list(product_ids))]
    fields = ["id", "name", "categ_id", "list_price", "default_code"]
    
    data = odoo_call("product.product", "search_read", domain, fields, limit=10000)
    return {p['id']: p for p in (data or [])}

@st.cache_data(ttl=CACHE_TTL)
def get_customers_with_location(year, company_id=None):
    """Get customers with their location data for mapping"""
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    
    # First get customer IDs from revenue
    domain = [
        ("date", ">=", start_date),
        ("date", "<=", end_date),
        ("account_id.code", "=like", "7%"),
        ("parent_state", "=", "posted"),
        ("partner_id", "!=", False)
    ]
    
    if company_id:
        domain.append(("company_id", "=", company_id))
    
    fields = ["partner_id", "balance"]
    revenue_data = odoo_call("account.move.line", "search_read", domain, fields, limit=RECORD_LIMIT)
    
    if not revenue_data:
        return None
    
    # Aggregate revenue by partner
    partner_revenue = {}
    for record in revenue_data:
        partner = record.get('partner_id')
        if partner:
            partner_id = partner[0]
            balance = record.get('balance', 0) or 0
            partner_revenue[partner_id] = partner_revenue.get(partner_id, 0) + balance
    
    # Get partner details including location
    partner_ids = list(partner_revenue.keys())
    if not partner_ids:
        return None
    
    partner_domain = [("id", "in", partner_ids)]
    partner_fields = ["id", "name", "city", "zip", "country_id", "street"]
    partners = odoo_call("res.partner", "search_read", partner_domain, partner_fields, limit=10000)
    
    if not partners:
        return None
    
    # Combine data
    result = []
    for partner in partners:
        partner_id = partner['id']
        revenue = -partner_revenue.get(partner_id, 0)  # Make positive
        if revenue > 0:
            result.append({
                'id': partner_id,
                'name': partner['name'],
                'city': partner.get('city', ''),
                'zip': partner.get('zip', ''),
                'country': partner.get('country_id', [None, ''])[1] if partner.get('country_id') else '',
                'revenue': revenue
            })
    
    return result

# =================================================================
# HELPER FUNCTIONS
# =================================================================

def format_currency(amount):
    """Format amount as Euro currency"""
    if amount is None:
        return "€ 0"
    if amount >= 0:
        return f"€ {amount:,.0f}".replace(',', '.')
    else:
        return f"-€ {abs(amount):,.0f}".replace(',', '.')

def filter_intercompany(data, exclude_ic=False):
    """Filter out intercompany transactions if requested"""
    if not exclude_ic or not data:
        return data
    
    return [
        record for record in data
        if not record.get('partner_id') or record['partner_id'][0] not in INTERCOMPANY_PARTNER_IDS
    ]

def calculate_monthly_totals(data, exclude_ic=False):
    """Calculate monthly totals from transaction data with optional IC filtering"""
    if not data:
        return {m: 0 for m in range(1, 13)}
    
    # Apply IC filter if needed
    if exclude_ic:
        data = filter_intercompany(data, exclude_ic)
    
    monthly = {m: 0 for m in range(1, 13)}
    for record in data:
        date_str = record.get('date', '')
        if date_str:
            try:
                month = int(date_str.split('-')[1])
                balance = record.get('balance', 0) or 0
                monthly[month] += balance
            except (ValueError, IndexError):
                pass
    return monthly

# =================================================================
# MAIN DASHBOARD
# =================================================================

def main():
    st.title("📊 LAB Groep Financial Dashboard")
    st.caption("v9 OPTIMIZED - Server-side aggregatie voor snellere laadtijden")
    
    # Sidebar configuration
    st.sidebar.header("⚙️ Instellingen")
    
    # API Key input (if not in secrets)
    api_key = get_api_key()
    if not api_key:
        st.sidebar.subheader("🔑 API Configuratie")
        api_key_input = st.sidebar.text_input(
            "Odoo API Key", 
            type="password",
            help="Voer je Odoo API key in. Deze wordt alleen in deze sessie opgeslagen."
        )
        if api_key_input:
            st.session_state.odoo_api_key = api_key_input
            st.rerun()
        else:
            st.warning("⚠️ Voer een Odoo API key in via de sidebar om data te laden.")
            st.info("💡 Tip: Voeg ODOO_API_KEY toe aan Streamlit Secrets voor permanente configuratie.")
            return
    
    # Data refresh button and cache info
    st.sidebar.markdown("---")
    col1, col2 = st.sidebar.columns([2, 1])
    with col1:
        if st.button("🔄 Ververs Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    with col2:
        st.caption(f"Cache: {CACHE_TTL//60}min")
    
    # Year selector
    current_year = datetime.now().year
    selected_year = st.sidebar.selectbox(
        "📅 Jaar",
        options=[current_year, current_year - 1, current_year - 2],
        index=0
    )
    
    # Company selector
    company_options = {"Alle bedrijven": None}
    company_options.update({name: id for id, name in COMPANIES.items()})
    
    selected_company_name = st.sidebar.selectbox(
        "🏢 Bedrijf",
        options=list(company_options.keys()),
        index=0
    )
    selected_company = company_options[selected_company_name]
    
    # Intercompany filter (for all views now)
    exclude_intercompany = st.sidebar.checkbox(
        "🔄 Exclusief intercompany",
        value=False,
        help="Filter intercompany transacties tussen LAB Shops, Conceptstore en Projects"
    )
    
    # =================================================================
    # TABS
    # =================================================================
    
    tab_overview, tab_revenue, tab_costs, tab_products, tab_map, tab_projects = st.tabs([
        "📈 Overzicht", "💰 Omzet", "📉 Kosten", "📦 Producten", "🗺️ Klantenkaart", "🏗️ Projecten"
    ])
    
    # =================================================================
    # TAB: OVERVIEW - OPTIMIZED with read_group
    # =================================================================
    with tab_overview:
        st.header(f"Financieel Overzicht {selected_year}")
        
        # Use fast functions when IC filter is off, legacy when on
        if exclude_intercompany:
            st.info("⚡ Intercompany filter actief - gebruikt gedetailleerde data")
            # Legacy mode for IC filtering
            with st.spinner("Data laden (gedetailleerd)..."):
                revenue_data = get_revenue_data(selected_year, selected_company)
                cost_data = get_cost_data(selected_year, selected_company)
                
                if revenue_data:
                    revenue_data = filter_intercompany(revenue_data, True)
                if cost_data:
                    cost_data = filter_intercompany(cost_data, True)
                
                revenue_monthly = calculate_monthly_totals(revenue_data) if revenue_data else {m: 0 for m in range(1, 13)}
                cost_monthly = calculate_monthly_totals(cost_data) if cost_data else {m: 0 for m in range(1, 13)}
                
                # Build dataframe
                rows = []
                for month in range(1, 13):
                    rev = -revenue_monthly.get(month, 0)
                    cost = cost_monthly.get(month, 0)
                    rows.append({
                        'Maand': MONTH_ABBREV_NL[month],
                        'Maand_Num': month,
                        'Omzet': rev,
                        'Kosten': cost,
                        'Winst': rev - cost
                    })
                df_monthly = pd.DataFrame(rows)
        else:
            # FAST mode with read_group
            with st.spinner("⚡ Data laden (geoptimaliseerd)..."):
                df_monthly = get_revenue_vs_cost_fast(selected_year, selected_company)
        
        if df_monthly is not None and not df_monthly.empty:
            # KPIs
            total_revenue = df_monthly['Omzet'].sum()
            total_costs = df_monthly['Kosten'].sum()
            total_profit = df_monthly['Winst'].sum()
            margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Totale Omzet", format_currency(total_revenue))
            col2.metric("Totale Kosten", format_currency(total_costs))
            col3.metric("Winst", format_currency(total_profit))
            col4.metric("Marge", f"{margin:.1f}%")
            
            # Monthly chart
            st.subheader("Maandelijks Overzicht")
            
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=df_monthly['Maand'],
                y=df_monthly['Omzet'],
                name='Omzet',
                marker_color='#2ecc71'
            ))
            fig.add_trace(go.Bar(
                x=df_monthly['Maand'],
                y=df_monthly['Kosten'],
                name='Kosten',
                marker_color='#e74c3c'
            ))
            fig.add_trace(go.Scatter(
                x=df_monthly['Maand'],
                y=df_monthly['Winst'],
                name='Winst',
                mode='lines+markers',
                line=dict(color='#3498db', width=3)
            ))
            
            fig.update_layout(
                barmode='group',
                xaxis_title='Maand',
                yaxis_title='Bedrag (€)',
                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # R/P status
            st.subheader("Debiteuren & Crediteuren")
            rp_data = get_receivables_payables(selected_company)
            if rp_data:
                col1, col2 = st.columns(2)
                col1.metric("Debiteuren (Openstaand)", format_currency(rp_data['receivables']))
                col2.metric("Crediteuren (Openstaand)", format_currency(rp_data['payables']))
        else:
            st.warning("Geen data beschikbaar. Controleer je API key.")
    
    # =================================================================
    # TAB: REVENUE (OMZET)
    # =================================================================
    with tab_revenue:
        st.header(f"💰 Omzet Analyse {selected_year}")
        
        # Get detailed revenue data for this tab
        with st.spinner("Omzet data laden..."):
            revenue_data = get_revenue_data(selected_year, selected_company)
            if exclude_intercompany:
                revenue_data = filter_intercompany(revenue_data, True)
        
        if revenue_data:
            total_revenue = -sum(r.get('balance', 0) or 0 for r in revenue_data)
            st.metric("Totale Omzet", format_currency(total_revenue))
            
            # Top customers
            st.subheader("🏆 Top 10 Klanten")
            top_customers = get_top_customers(selected_year, selected_company)
            
            if top_customers:
                # Filter IC if needed
                if exclude_intercompany:
                    top_customers = [c for c in top_customers if c['partner_id'] not in INTERCOMPANY_PARTNER_IDS]
                
                df_customers = pd.DataFrame(top_customers[:10])
                df_customers['revenue_formatted'] = df_customers['revenue'].apply(format_currency)
                
                fig = px.bar(
                    df_customers,
                    x='revenue',
                    y='name',
                    orientation='h',
                    title='Top 10 Klanten op Omzet',
                    labels={'revenue': 'Omzet (€)', 'name': 'Klant'}
                )
                fig.update_layout(yaxis={'categoryorder': 'total ascending'}, height=400)
                st.plotly_chart(fig, use_container_width=True)
                
                # Table view
                st.dataframe(
                    df_customers[['name', 'revenue_formatted']].rename(
                        columns={'name': 'Klant', 'revenue_formatted': 'Omzet'}
                    ),
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.warning("Geen omzet data beschikbaar.")
    
    # =================================================================
    # TAB: COSTS (KOSTEN)
    # =================================================================
    with tab_costs:
        st.header(f"📉 Kosten Analyse {selected_year}")
        
        with st.spinner("Kosten data laden..."):
            cost_data = get_cost_data(selected_year, selected_company)
            if exclude_intercompany:
                cost_data = filter_intercompany(cost_data, True)
        
        if cost_data:
            total_costs = sum(r.get('balance', 0) or 0 for r in cost_data)
            st.metric("Totale Kosten", format_currency(total_costs))
            
            # Top suppliers
            st.subheader("🏭 Top 10 Leveranciers")
            top_suppliers = get_top_suppliers(selected_year, selected_company)
            
            if top_suppliers:
                # Filter IC if needed
                if exclude_intercompany:
                    top_suppliers = [s for s in top_suppliers if s['partner_id'] not in INTERCOMPANY_PARTNER_IDS]
                
                df_suppliers = pd.DataFrame(top_suppliers[:10])
                df_suppliers['cost_formatted'] = df_suppliers['cost'].apply(format_currency)
                
                fig = px.bar(
                    df_suppliers,
                    x='cost',
                    y='name',
                    orientation='h',
                    title='Top 10 Leveranciers op Kosten',
                    labels={'cost': 'Kosten (€)', 'name': 'Leverancier'}
                )
                fig.update_layout(yaxis={'categoryorder': 'total ascending'}, height=400)
                st.plotly_chart(fig, use_container_width=True)
                
                # Table view
                st.dataframe(
                    df_suppliers[['name', 'cost_formatted']].rename(
                        columns={'name': 'Leverancier', 'cost_formatted': 'Kosten'}
                    ),
                    use_container_width=True,
                    hide_index=True
                )
        else:
            st.warning("Geen kosten data beschikbaar.")
    
    # =================================================================
    # TAB: PRODUCTS
    # =================================================================
    with tab_products:
        st.header(f"📦 Product Analyse {selected_year}")
        
        product_tab1, product_tab2 = st.tabs(["📊 Product Verkopen", "🛒 POS Analyse"])
        
        with product_tab1:
            with st.spinner("Product data laden..."):
                product_data = get_product_sales(selected_year, selected_company)
            
            if product_data:
                # Aggregate by product
                product_totals = {}
                for record in product_data:
                    product = record.get('product_id')
                    if product:
                        product_id = product[0]
                        product_name = product[1]
                        balance = record.get('balance', 0) or 0
                        qty = record.get('quantity', 0) or 0
                        
                        if product_id not in product_totals:
                            product_totals[product_id] = {'name': product_name, 'revenue': 0, 'quantity': 0}
                        product_totals[product_id]['revenue'] += -balance
                        product_totals[product_id]['quantity'] += qty
                
                # Sort by revenue
                sorted_products = sorted(product_totals.items(), key=lambda x: x[1]['revenue'], reverse=True)
                
                # Display top 20
                top_products = sorted_products[:20]
                df_products = pd.DataFrame([{
                    'Product': p[1]['name'],
                    'Omzet': p[1]['revenue'],
                    'Aantal': abs(p[1]['quantity'])
                } for p in top_products])
                
                if not df_products.empty:
                    st.subheader("🏆 Top 20 Producten op Omzet")
                    
                    fig = px.bar(
                        df_products,
                        x='Omzet',
                        y='Product',
                        orientation='h',
                        title='Top 20 Producten'
                    )
                    fig.update_layout(yaxis={'categoryorder': 'total ascending'}, height=600)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    df_products['Omzet_fmt'] = df_products['Omzet'].apply(format_currency)
                    st.dataframe(
                        df_products[['Product', 'Omzet_fmt', 'Aantal']].rename(
                            columns={'Omzet_fmt': 'Omzet'}
                        ),
                        use_container_width=True,
                        hide_index=True
                    )
            else:
                st.warning("Geen product data beschikbaar.")
        
        with product_tab2:
            st.subheader("🛒 POS Verkopen (LAB Conceptstore)")
            
            # POS is mainly for LAB Conceptstore (company_id=3)
            pos_company = 3 if selected_company is None else selected_company
            
            with st.spinner("POS data laden..."):
                pos_orders = get_pos_orders(selected_year, pos_company)
            
            if pos_orders:
                total_pos = sum(o.get('amount_total', 0) or 0 for o in pos_orders)
                order_count = len(pos_orders)
                avg_order = total_pos / order_count if order_count > 0 else 0
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Totaal POS Omzet", format_currency(total_pos))
                col2.metric("Aantal Orders", f"{order_count:,}")
                col3.metric("Gem. Orderwaarde", format_currency(avg_order))
                
                # Monthly POS trend
                st.subheader("📈 POS Omzet per Maand")
                
                monthly_pos = {m: 0 for m in range(1, 13)}
                for order in pos_orders:
                    date_str = order.get('date_order', '')
                    if date_str:
                        try:
                            month = int(date_str.split('-')[1])
                            monthly_pos[month] += order.get('amount_total', 0) or 0
                        except:
                            pass
                
                df_pos_monthly = pd.DataFrame([
                    {'Maand': MONTH_ABBREV_NL[m], 'Omzet': monthly_pos[m]}
                    for m in range(1, 13)
                ])
                
                fig = px.bar(
                    df_pos_monthly,
                    x='Maand',
                    y='Omzet',
                    title='POS Omzet per Maand'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Geen POS data beschikbaar voor deze periode.")
    
    # =================================================================
    # TAB: CUSTOMER MAP
    # =================================================================
    with tab_map:
        st.header(f"🗺️ Klantenlocaties {selected_year}")
        
        with st.spinner("Klantlocaties laden..."):
            customer_locations = get_customers_with_location(selected_year, selected_company)
        
        if customer_locations:
            # Filter customers with city info
            customers_with_city = [c for c in customer_locations if c.get('city')]
            
            if customers_with_city:
                st.metric("Klanten met locatie", len(customers_with_city))
                
                # Group by city
                city_totals = {}
                for c in customers_with_city:
                    city = c['city']
                    if city not in city_totals:
                        city_totals[city] = {'revenue': 0, 'count': 0}
                    city_totals[city]['revenue'] += c['revenue']
                    city_totals[city]['count'] += 1
                
                # Top cities
                sorted_cities = sorted(city_totals.items(), key=lambda x: x[1]['revenue'], reverse=True)
                
                st.subheader("🏙️ Top 15 Steden op Omzet")
                df_cities = pd.DataFrame([{
                    'Stad': city,
                    'Omzet': data['revenue'],
                    'Aantal Klanten': data['count']
                } for city, data in sorted_cities[:15]])
                
                if not df_cities.empty:
                    fig = px.bar(
                        df_cities,
                        x='Stad',
                        y='Omzet',
                        title='Omzet per Stad',
                        color='Aantal Klanten',
                        color_continuous_scale='Blues'
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    
                    df_cities['Omzet_fmt'] = df_cities['Omzet'].apply(format_currency)
                    st.dataframe(
                        df_cities[['Stad', 'Omzet_fmt', 'Aantal Klanten']].rename(
                            columns={'Omzet_fmt': 'Omzet'}
                        ),
                        use_container_width=True,
                        hide_index=True
                    )
            else:
                st.warning("Geen klanten met stadsgegevens gevonden.")
        else:
            st.warning("Geen klantlocatie data beschikbaar.")
    
    # =================================================================
    # TAB: PROJECTS (LAB Projects specific)
    # =================================================================
    with tab_projects:
        st.header(f"🏗️ LAB Projects Analyse {selected_year}")
        
        # Force LAB Projects company
        projects_company = 4
        
        with st.spinner("Project data laden..."):
            revenue_data = get_revenue_data(selected_year, projects_company)
            cost_data = get_cost_data(selected_year, projects_company)
        
        if revenue_data:
            total_revenue = -sum(r.get('balance', 0) or 0 for r in revenue_data)
            total_costs = sum(r.get('balance', 0) or 0 for r in (cost_data or []))
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Omzet LAB Projects", format_currency(total_revenue))
            col2.metric("Kosten LAB Projects", format_currency(total_costs))
            col3.metric("Marge", format_currency(total_revenue - total_costs))
            
            # Verf & Behang analysis - DYNAMIC based on selected_year
            st.subheader(f"🎨 Verf & Behang Analyse {selected_year}")
            
            # Get product sales for analysis
            product_sales = get_product_sales(selected_year, projects_company)
            
            if product_sales:
                # Categorize products
                verf_keywords = ['verf', 'paint', 'lak', 'primer', 'grondverf']
                behang_keywords = ['behang', 'wallpaper', 'wandbekleding']
                
                verf_total = 0
                behang_total = 0
                other_total = 0
                
                for record in product_sales:
                    product = record.get('product_id')
                    if product:
                        product_name = product[1].lower() if product[1] else ''
                        revenue = -(record.get('balance', 0) or 0)
                        
                        if any(kw in product_name for kw in verf_keywords):
                            verf_total += revenue
                        elif any(kw in product_name for kw in behang_keywords):
                            behang_total += revenue
                        else:
                            other_total += revenue
                
                col1, col2, col3 = st.columns(3)
                col1.metric("🎨 Verf", format_currency(verf_total))
                col2.metric("📜 Behang", format_currency(behang_total))
                col3.metric("📦 Overig", format_currency(other_total))
                
                # Pie chart
                if verf_total > 0 or behang_total > 0:
                    fig = px.pie(
                        values=[verf_total, behang_total, other_total],
                        names=['Verf', 'Behang', 'Overig'],
                        title=f'Product Categorieën {selected_year}'
                    )
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Geen product verkopen gevonden voor LAB Projects.")
        else:
            st.warning("Geen data beschikbaar voor LAB Projects.")

if __name__ == "__main__":
    main()
