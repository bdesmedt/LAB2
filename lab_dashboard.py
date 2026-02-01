"""
LAB Groep Financial Dashboard v13
=================================
Wijzigingen t.o.v. v12:
- 🧾 BTW Analyse module toegevoegd aan Maandafsluiting
  - Checkbox voor maandelijkse vs kwartaal BTW aangifte
  - Automatische periode berekening (Q1-Q4 of per maand)
  - BTW overzicht met voorbelasting, af te dragen, en netto positie
  - Vergelijking met vorige periode (maand of kwartaal)
  - Detail tabel per BTW rekening
  - 🤖 AI Analyse knop: laat AI afwijkingen analyseren en verklaren
  - Waarschuwing bij grote BTW afwijkingen (>25%)

Wijzigingen in v12:
- 📋 Maandafsluiting (Financial Close) tab toegevoegd
  - Wachtwoord-beveiligde toegang voor gevoelige financiële afsluitingen
  - Periode-selectie (maand/jaar/entiteit)
  - Financiële kerncijfers met vergelijking t.o.v. vorige maand
  - Validatie controles (balans, ongeboekte entries, oude debiteuren)
  - 6-maanden trend analyse met grafieken
  - Aandachtspunten highlighting
  - Export functionaliteit (JSON, CSV, TXT rapport)
  - Graceful degradation: dashboard werkt zonder wachtwoord configuratie

Eerdere features (v11):
- 💬 AI Chatbot tab (OpenAI GPT-4)
- ✅ Nederlandse benamingen voor alle rekeningen/categorieën (nl_NL context)
- ✅ Balans tab met Kwadrant format (ACTIVA | PASSIVA)
- ✅ Intercompany filter werkt nu ook op week/dag omzet
- ✅ Aparte tab met banksaldi per rekening per entiteit
- ✅ Factuur drill-down met PDF/Odoo link
- ✅ Kostendetail per categorie
- ✅ Cashflow prognose
- ✅ LAB Projects: Verf vs Behang analyse
- ✅ Klantenkaart voor LAB Projects
"""

# Fallback package installer voor Streamlit Cloud
import subprocess
import sys

def install_packages():
    packages = ['plotly', 'pandas', 'requests', 'folium', 'streamlit-folium']
    for package in packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', package, '-q'])

install_packages()

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import json
from datetime import datetime, timedelta
from functools import lru_cache
import base64

# =============================================================================
# CONFIGURATIE
# =============================================================================

st.set_page_config(
    page_title="LAB Groep Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Odoo configuratie
ODOO_URL = "https://lab.odoo.works/jsonrpc"
ODOO_DB = "bluezebra-works-nl-vestingh-production-13415483"
ODOO_UID = 37

# API Key - probeer secrets, anders gebruik session state (input in main)
def get_api_key():
    # Probeer eerst uit secrets
    try:
        key = st.secrets.get("ODOO_API_KEY", "")
        if key:
            return key
    except:
        pass
    
    # Fallback: uit session state (wordt gezet in main())
    return st.session_state.get("api_key", "")

COMPANIES = {
    1: "LAB Conceptstore",
    2: "LAB Shops",
    3: "LAB Projects"
}

# =============================================================================
# FINANCIAL CLOSE PASSWORD FUNCTIONS
# =============================================================================

def get_financial_close_password():
    """
    Get Financial Close password from secrets or environment.
    Returns empty string if not configured (graceful degradation).
    """
    # Try Streamlit secrets first
    try:
        password = st.secrets.get("FINANCIAL_CLOSE_PASSWORD", "")
        if password:
            return password
    except:
        pass

    # Fallback: try environment variable
    import os
    return os.environ.get("FINANCIAL_CLOSE_PASSWORD", "")

def verify_financial_close_password(input_password):
    """
    Verify the input password against the configured password.
    Uses simple string comparison (can be enhanced with hashing if needed).
    Returns: (is_valid: bool, error_message: str or None)
    """
    configured_password = get_financial_close_password()

    # Check if password is configured
    if not configured_password:
        return False, "no_password_configured"

    # Verify password
    if input_password == configured_password:
        return True, None
    else:
        return False, "invalid_password"

def is_financial_close_configured():
    """Check if Financial Close password is configured in the system."""
    return bool(get_financial_close_password())

# =============================================================================
# NEDERLANDSE VERTALINGEN (UITGEBREID)
# =============================================================================

# Categorie vertalingen (voor kostencategorieën 40-49)
CATEGORY_TRANSLATIONS = {
    "40": "Personeelskosten",
    "41": "Huisvestingskosten",
    "42": "Vervoerskosten",
    "43": "Kantoorkosten",
    "44": "Marketing & Reclame",
    "45": "Algemene Kosten",
    "46": "Overige Bedrijfskosten",
    "47": "Financiële Lasten",
    "48": "Afschrijvingen",
    "49": "Overige Kosten",
    "70": "Kostprijs Verkopen",
    "71": "Kostprijs Verkopen",
    "72": "Kostprijs Verkopen",
    "73": "Kostprijs Verkopen",
    "74": "Kostprijs Verkopen",
    "75": "Kostprijs Verkopen",
    "80": "Omzet",
    "81": "Omzet",
    "82": "Omzet",
    "83": "Omzet",
    "84": "Omzet",
    "85": "Omzet"
}

# Uitgebreide rekening vertalingen
ACCOUNT_TRANSLATIONS = {
    # Personeelskosten (40)
    "Gross wages": "Brutolonen",
    "Bonuses and commissions": "Bonussen en provisies",
    "Holiday allowance": "Vakantietoeslag",
    "Royalty": "Tantièmes",
    "Employee car contribution": "Eigen bijdrage auto",
    "Healthcare Insurance Act (SVW) contribution": "ZVW-bijdrage",
    "Employer's share of payroll taxes": "Werkgeverslasten loonheffing",
    "Employer's share of pensions": "Pensioenpremie werkgever",
    "Employer's share of social security contributions": "Sociale lasten werkgever",
    "Provision for holidays": "Reservering vakantiedagen",
    "Compensation for commuting": "Reiskostenvergoeding",
    "Reimbursement of study costs": "Studiekostenvergoeding",
    "Reimbursement of other travel expenses": "Overige reiskostenvergoeding",
    "Reimbursement of other expenses": "Overige onkostenvergoeding",
    "Management fees": "Managementvergoeding",
    "Staff on loan": "Ingehuurd personeel",
    "Working expenses scheme (WKR max 1.2% gross pay)": "Werkkostenregeling (WKR)",
    "Travel costs of hired staff": "Reiskosten ingehuurd personeel",
    "Recharge of direct labour costs": "Doorbelaste personeelskosten",
    "Sick leave insurance": "Verzuimverzekering",
    "Canteen costs": "Kantinekosten",
    "Corporate clothing": "Bedrijfskleding",
    "Other travel expenses": "Overige reiskosten",
    "Conferences, seminars and symposia": "Congressen en seminars",
    "Staff recruitment costs": "Wervingskosten personeel",
    "Study and training costs": "Opleidingskosten",
    "Other personnel costs": "Overige personeelskosten",
    "Temporary staff": "Uitzendkrachten",
    
    # Huisvestingskosten (41)
    "Property rental": "Huur bedrijfspand",
    "Major property maintenance": "Groot onderhoud pand",
    "Small property maintenance": "Klein onderhoud pand",
    "Cleaning and window cleaning": "Schoonmaak en glazenwassen",
    "Gas": "Gas",
    "Electricity": "Elektriciteit",
    "Water": "Water",
    "Property insurance": "Opstalverzekering",
    "Property taxes": "Onroerendezaakbelasting",
    "Other property costs": "Overige huisvestingskosten",
    
    # Vervoerskosten (42)
    "Car leasing": "Autoleasing",
    "Fuel costs": "Brandstofkosten",
    "Repair and maintenance": "Reparatie en onderhoud",
    "Motor vehicle insurance": "Motorrijtuigenverzekering",
    "Motor vehicle tax": "Motorrijtuigenbelasting",
    "Transport costs": "Transportkosten",
    "Other vehicle costs": "Overige autokosten",
    "Parking costs": "Parkeerkosten",
    
    # Kantoorkosten (43)
    "Office supplies": "Kantoorbenodigdheden",
    "Printing and copying": "Drukwerk en kopieerkosten",
    "Telephone and fax": "Telefoon en fax",
    "Internet costs": "Internetkosten",
    "Postage costs": "Portokosten",
    "Software": "Software",
    "Computer costs": "Computerkosten",
    "Other office costs": "Overige kantoorkosten",
    
    # Marketing & Reclame (44)
    "Advertising costs": "Advertentiekosten",
    "Promotional material": "Promotiemateriaal",
    "Trade fairs and exhibitions": "Beurzen en exposities",
    "Website costs": "Websitekosten",
    "Public relations": "Public relations",
    "Sponsoring": "Sponsoring",
    "Other marketing costs": "Overige marketingkosten",
    
    # Algemene Kosten (45)
    "External advice": "Extern advies",
    "Accountant costs": "Accountantskosten",
    "Legal costs": "Juridische kosten",
    "Audit fees": "Controlekosten",
    "Consultancy fees": "Advieskosten",
    "Administration costs": "Administratiekosten",
    "Collection costs": "Incassokosten",
    "Other external costs": "Overige externe kosten",
    
    # Overige Bedrijfskosten (46)
    "Bank charges": "Bankkosten",
    "Payment service charges": "Betalingsverkeerskosten",
    "Insurance": "Verzekeringen",
    "Subscriptions and memberships": "Abonnementen en lidmaatschappen",
    "Gifts and donations": "Giften en donaties",
    "Entertainment expenses": "Representatiekosten",
    "Other operating costs": "Overige bedrijfskosten",
    
    # Financiële Lasten (47)
    "Interest expenses": "Rentelasten",
    "Bank interest": "Bankrente",
    "Interest on loans": "Rente op leningen",
    "Interest and similar charges": "Rente en soortgelijke kosten",
    "Exchange differences": "Koersverschillen",
    "Other financial costs": "Overige financiële kosten",
    
    # Afschrijvingen (48)
    "Depreciation of buildings": "Afschrijving gebouwen",
    "Depreciation of machines": "Afschrijving machines",
    "Depreciation of passenger cars": "Afschrijving personenauto's",
    "Depreciation of other transport equipment": "Afschrijving overig vervoer",
    "Depreciation of trucks": "Afschrijving vrachtwagens",
    "Depreciation of furniture and fixtures": "Afschrijving inventaris",
    "Depreciation of computer equipment": "Afschrijving computers",
    "Depreciation of intangible assets": "Afschrijving immateriële activa",
    "Other depreciation": "Overige afschrijvingen",
    "Depreciation of tools": "Afschrijving gereedschap",
    
    # Omzet (80)
    "Product sales": "Productverkopen",
    "Service revenue": "Omzet diensten",
    "Other revenue": "Overige omzet",
    "Revenue from goods": "Omzet goederen",
    "Domestic sales": "Binnenlandse verkopen",
    "Export sales": "Exportverkopen",
    "Intercompany sales": "Intercompany verkopen",
    
    # Kostprijs verkopen (70)
    "Cost of goods sold": "Kostprijs verkopen",
    "Cost of materials": "Materiaalkosten",
    "Direct labour costs": "Directe loonkosten",
    "Production costs": "Productiekosten",
    "Purchase costs": "Inkoopkosten",
    "Subcontracting": "Uitbesteed werk",
    
    # Balansposten
    "Accounts receivable": "Debiteuren",
    "Accounts payable": "Crediteuren",
    "Bank": "Bank",
    "Cash": "Kas",
    "Prepaid expenses": "Vooruitbetaalde kosten",
    "Accrued expenses": "Nog te betalen kosten",
    "VAT receivable": "Te vorderen BTW",
    "VAT payable": "Af te dragen BTW",
    "Inventory": "Voorraad",
    "Fixed assets": "Vaste activa",
    
    # Intercompany
    "Intercompany receivables": "Vordering groepsmaatschappijen",
    "Intercompany payables": "Schuld groepsmaatschappijen",
    "Current account": "Rekening-courant"
}

def translate_account_name(name):
    """Vertaal Engelse rekeningnaam naar Nederlands indien beschikbaar"""
    if not name:
        return name
    # Eerst exacte match proberen
    if name in ACCOUNT_TRANSLATIONS:
        return ACCOUNT_TRANSLATIONS[name]
    # Dan gedeeltelijke match
    for eng, nl in ACCOUNT_TRANSLATIONS.items():
        if eng.lower() in name.lower():
            return name.replace(eng, nl)
    return name

def get_category_name(account_code):
    """Haal Nederlandse categorienaam op basis van rekeningcode"""
    if not account_code or len(str(account_code)) < 2:
        return "Overig"
    prefix = str(account_code)[:2]
    return CATEGORY_TRANSLATIONS.get(prefix, f"Categorie {prefix}")

# =============================================================================
# ODOO API HELPERS
# =============================================================================

def odoo_call(model, method, domain, fields, limit=None, timeout=120, include_archived=False):
    """Generieke Odoo JSON-RPC call met verbeterde timeout handling"""
    api_key = get_api_key()
    if not api_key:
        return []
    
    args = [ODOO_DB, ODOO_UID, api_key, model, method, [domain]]
    kwargs = {"fields": fields}
    if limit:
        kwargs["limit"] = limit
    # Always use Dutch language, optionally include archived records
    context = {"lang": "nl_NL"}
    if include_archived:
        context["active_test"] = False
    kwargs["context"] = context
    args.append(kwargs)
    
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": args
        },
        "id": 1
    }
    
    try:
        response = requests.post(ODOO_URL, json=payload, timeout=timeout)
        result = response.json()
        if "error" in result:
            st.error(f"Odoo error: {result['error']}")
            return []
        return result.get("result", [])
    except requests.exceptions.Timeout:
        st.error("⏱️ Timeout - probeer een kortere periode of specifieke entiteit")
        return []
    except Exception as e:
        st.error(f"Connection error: {e}")
        return []

# =============================================================================
# OPENAI CHATBOT HELPERS
# =============================================================================

CHATBOT_SYSTEM_PROMPT = """Je bent een financieel assistent voor LAB Groep, een holding met meerdere bedrijven.
Je hebt toegang tot de Odoo boekhouding en kunt vragen beantwoorden over:
- Omzet en kosten
- Facturen (debiteuren en crediteuren)
- Banksaldi
- Klanten en leveranciers
- Producten en categorieën
- Cashflow en balans

BEDRIJVEN (company_id):
- 1: LAB Shops (retail)
- 2: LAB Projects (projecten/behang/verf)
- 3: LAB Holding (holding)
- 4: Verf en Wand (verf specialist)
- 5: Vestingh Art of Living (premium interieur)

BELANGRIJKE ODOO MODELLEN:
- account.move: Facturen/boekingen (move_type: 'out_invoice'=verkoopfactuur, 'in_invoice'=inkoopfactuur)
  Belangrijke velden:
  - name: factuurnummer
  - partner_id: klant/leverancier
  - invoice_date: factuurdatum
  - invoice_date_due: vervaldatum
  - amount_total: totaalbedrag
  - amount_residual: openstaand bedrag (0 = betaald)
  - state: 'draft'=concept, 'posted'=geboekt, 'cancel'=geannuleerd
  - payment_state: 'not_paid'=niet betaald, 'partial'=deels betaald, 'paid'=betaald, 'reversed'=teruggedraaid
  - ref: referentie/omschrijving
  - company_id: bedrijf
- account.move.line: Boekingsregels (debit/credit, account_id, partner_id)
- res.partner: Klanten/leveranciers (name, street, zip, city, country_id, supplier_rank, customer_rank)
- product.product: Producten
- account.account: Grootboekrekeningen

VOORBEELD QUERY VOOR FACTUURSTATUS:
```odoo_query
{
    "model": "account.move",
    "domain": [["move_type", "=", "in_invoice"], ["invoice_date", ">=", "2025-01-01"], ["state", "=", "posted"]],
    "fields": ["name", "partner_id", "invoice_date", "amount_total", "amount_residual", "payment_state", "ref"],
    "limit": 100
}
```

REKENINGSTRUCTUUR:
- 8xxx: Omzet rekeningen
- 4xxx, 6xxx, 7xxx: Kostenrekeningen  
- 1xxx: Activa (bank: 1100-1199)
- 0xxx: Vaste activa
- 2xxx: Passiva

INTERCOMPANY PARTNERS (filter deze uit voor externe analyse):
IDs: [1, 2, 3, 4, 23, 24, 4509, 20618, 74170, 79863]

Als je Odoo data nodig hebt, genereer een JSON query in dit formaat:
```odoo_query
{
    "model": "account.move.line",
    "domain": [["date", ">=", "2025-01-01"], ["date", "<=", "2025-12-31"]],
    "fields": ["name", "debit", "credit", "partner_id"],
    "groupby": ["partner_id"],
    "limit": 100
}
```

Geef ALTIJD bedragen in Euro's met juiste opmaak (€1.234,56).
Antwoord in het Nederlands, bondig maar informatief.

BELANGRIJK: Genereer ALTIJD een odoo_query wanneer de gebruiker vraagt naar:
- Factuurstatus of openstaande facturen
- Welke leveranciers/klanten facturen hebben
- Betaalstatus van facturen
- Specifieke transacties of bedragen

Zeg NOOIT dat je iets niet kunt opvragen als het via bovenstaande modellen beschikbaar is.
Als je echt geen data kunt vinden na een query, geef dat aan met de resultaten."""

def get_openai_key():
    """Haal OpenAI API key op - probeer secrets, anders session state"""
    # Probeer eerst uit secrets
    try:
        key = st.secrets.get("OPENAI_API_KEY", "")
        if key:
            return key
    except:
        pass

    # Fallback: uit session state (wordt gezet in main())
    return st.session_state.get("openai_key", "")

def call_openai(messages, model="gpt-4o-mini"):
    """Roep OpenAI API aan"""
    api_key = get_openai_key()
    if not api_key:
        return None, "Geen OpenAI API key geconfigureerd"
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 2000
            },
            timeout=60
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"], None
        else:
            return None, f"OpenAI error: {response.status_code} - {response.text}"
    except Exception as e:
        return None, f"OpenAI connection error: {e}"

def execute_odoo_query(query_json):
    """Voer een Odoo query uit op basis van chatbot instructies"""
    try:
        query = json.loads(query_json)
        model = query.get("model", "account.move.line")
        domain = query.get("domain", [])
        fields = query.get("fields", [])
        groupby = query.get("groupby", [])
        limit = query.get("limit", 100)
        
        if groupby:
            # Gebruik read_group voor geaggregeerde data
            result = odoo_read_group(model, domain, fields, groupby)
        else:
            # Gebruik normale search_read
            result = odoo_call(model, "search_read", domain, fields, limit=limit)
        
        return result, None
    except Exception as e:
        return None, f"Query error: {e}"

def process_chat_message(user_message, chat_history, context_info):
    """Verwerk een chat bericht en genereer antwoord"""
    
    # Bouw berichten op voor OpenAI
    messages = [
        {"role": "system", "content": CHATBOT_SYSTEM_PROMPT + f"\n\nHuidige context:\n{context_info}"}
    ]
    
    # Voeg chat geschiedenis toe
    for msg in chat_history[-10:]:  # Laatste 10 berichten
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    # Voeg nieuwe vraag toe
    messages.append({"role": "user", "content": user_message})
    
    # Eerste OpenAI call
    response, error = call_openai(messages)
    if error:
        return f"❌ {error}", None
    
    # Check of er een Odoo query in het antwoord zit
    if "```odoo_query" in response:
        import re
        query_match = re.search(r'```odoo_query\s*\n(.*?)\n```', response, re.DOTALL)
        if query_match:
            query_json = query_match.group(1)
            query_result, query_error = execute_odoo_query(query_json)
            
            if query_error:
                return f"❌ Query fout: {query_error}", None
            
            # Tweede call met query resultaten
            messages.append({"role": "assistant", "content": response})
            messages.append({
                "role": "user", 
                "content": f"Hier zijn de resultaten van de Odoo query:\n```json\n{json.dumps(query_result[:50], indent=2, default=str)}\n```\nGeef nu een duidelijk antwoord op basis van deze data."
            })
            
            final_response, error = call_openai(messages)
            if error:
                return f"❌ {error}", query_result
            return final_response, query_result
    
    return response, None

# =============================================================================
# DATA FUNCTIES
# =============================================================================

@st.cache_data(ttl=300)
def get_bank_balances():
    """Haal alle banksaldi op per rekening (excl. R/C intercompany)"""
    journals = odoo_call(
        "account.journal", "search_read",
        [["type", "=", "bank"]],
        ["name", "company_id", "default_account_id", "current_statement_balance", "code"]
    )
    
    # Haal account codes op voor de journals om R/C te kunnen filteren
    account_ids = [j.get("default_account_id", [None])[0] for j in journals if j.get("default_account_id")]
    accounts = {}
    if account_ids:
        account_data = odoo_call(
            "account.account", "search_read",
            [["id", "in", account_ids]],
            ["id", "code", "name"]
        )
        accounts = {a["id"]: a for a in account_data}
    
    # Filter: echte bankrekeningen vs R/C intercompany
    bank_only = []
    for j in journals:
        name = j.get("name", "")
        account_id = j.get("default_account_id", [None])[0]
        account_code = accounts.get(account_id, {}).get("code", "") if account_id else ""
        
        # R/C detectie: naam bevat R/C OF rekeningcode begint met 12 of 14
        is_rc = (
            "R/C" in name or 
            "RC " in name or
            str(account_code).startswith("12") or  # Vorderingen op groepsmaatschappijen
            str(account_code).startswith("14")     # Schulden aan groepsmaatschappijen
        )
        
        if not is_rc:
            bank_only.append(j)
    
    return bank_only

@st.cache_data(ttl=300)
def get_rc_balances():
    """Haal R/C (Rekening Courant) intercompany saldi op"""
    journals = odoo_call(
        "account.journal", "search_read",
        [["type", "=", "bank"]],
        ["name", "company_id", "default_account_id", "current_statement_balance", "code"]
    )
    
    # Haal account codes op voor de journals
    account_ids = [j.get("default_account_id", [None])[0] for j in journals if j.get("default_account_id")]
    accounts = {}
    if account_ids:
        account_data = odoo_call(
            "account.account", "search_read",
            [["id", "in", account_ids]],
            ["id", "code", "name"]
        )
        accounts = {a["id"]: a for a in account_data}
    
    # Filter: alleen R/C rekeningen
    rc_only = []
    for j in journals:
        name = j.get("name", "")
        account_id = j.get("default_account_id", [None])[0]
        account_code = accounts.get(account_id, {}).get("code", "") if account_id else ""
        
        # R/C detectie
        is_rc = (
            "R/C" in name or 
            "RC " in name or
            str(account_code).startswith("12") or
            str(account_code).startswith("14")
        )
        
        if is_rc:
            # Voeg account code toe aan journal voor weergave
            j["account_code"] = account_code
            j["account_type"] = "Vordering" if str(account_code).startswith("12") else "Schuld"
            rc_only.append(j)
    
    return rc_only

# Intercompany partner IDs (LAB Conceptstore, LAB Shops, LAB Projects)
# Verplaatst naar boven voor gebruik in aggregatie functies
INTERCOMPANY_PARTNERS = [1, 7, 8]

def odoo_read_group(model, domain, fields, groupby, timeout=120):
    """Odoo read_group voor server-side aggregatie - GEEN limiet!
    
    Inclusief gearchiveerde records (active_test: False) zodat transacties
    met gearchiveerde contacten ook meekomen.
    """
    api_key = get_api_key()
    if not api_key:
        return []
    
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "object",
            "method": "execute_kw",
            "args": [ODOO_DB, ODOO_UID, api_key, model, "read_group", 
                    [domain], {
                        "fields": fields, 
                        "groupby": groupby, 
                        "lazy": False,
                        "context": {"active_test": False, "lang": "nl_NL"}  # Inclusief gearchiveerde records + Nederlandse taal
                    }]
        },
        "id": 1
    }
    
    try:
        response = requests.post(ODOO_URL, json=payload, timeout=timeout)
        result = response.json()
        if "error" in result:
            st.error(f"Odoo read_group error: {result['error']}")
            return []
        return result.get("result", [])
    except Exception as e:
        st.error(f"Read group error: {e}")
        return []

@st.cache_data(ttl=3600)  # 1 uur cache
def get_revenue_aggregated(year, company_id=None):
    """Server-side geaggregeerde omzetdata - geen limiet!"""
    domain = [
        ("account_id.code", ">=", "800000"),
        ("account_id.code", "<", "900000"),
        ("date", ">=", f"{year}-01-01"),
        ("date", "<=", f"{year}-12-31"),
        ("parent_state", "=", "posted")
    ]
    if company_id:
        domain.append(("company_id", "=", company_id))
    
    # Groepeer per maand
    result = odoo_read_group("account.move.line", domain, ["balance:sum"], ["date:month"])
    return result

@st.cache_data(ttl=3600)  # 1 uur cache
def get_cost_aggregated(year, company_id=None):
    """Server-side geaggregeerde kostendata - geen limiet!"""
    # Query voor 4* rekeningen
    domain_4 = [
        ("account_id.code", ">=", "400000"),
        ("account_id.code", "<", "500000"),
        ("date", ">=", f"{year}-01-01"),
        ("date", "<=", f"{year}-12-31"),
        ("parent_state", "=", "posted")
    ]
    if company_id:
        domain_4.append(("company_id", "=", company_id))
    
    # Query voor 6* rekeningen
    domain_6 = [
        ("account_id.code", ">=", "600000"),
        ("account_id.code", "<", "700000"),
        ("date", ">=", f"{year}-01-01"),
        ("date", "<=", f"{year}-12-31"),
        ("parent_state", "=", "posted")
    ]
    if company_id:
        domain_6.append(("company_id", "=", company_id))
    
    # Query voor 7* rekeningen (kostprijs verkopen)
    domain_7 = [
        ("account_id.code", ">=", "700000"),
        ("account_id.code", "<", "800000"),
        ("date", ">=", f"{year}-01-01"),
        ("date", "<=", f"{year}-12-31"),
        ("parent_state", "=", "posted")
    ]
    if company_id:
        domain_7.append(("company_id", "=", company_id))
    
    result_4 = odoo_read_group("account.move.line", domain_4, ["balance:sum"], ["date:month"])
    result_6 = odoo_read_group("account.move.line", domain_6, ["balance:sum"], ["date:month"])
    result_7 = odoo_read_group("account.move.line", domain_7, ["balance:sum"], ["date:month"])
    
    # Combineer resultaten per maand
    monthly = {}
    for r in result_4 + result_6 + result_7:
        month = r.get("date:month", "Unknown")
        if month not in monthly:
            monthly[month] = 0
        monthly[month] += r.get("balance", 0)
    
    return [{"date:month": k, "balance": v} for k, v in monthly.items()]

@st.cache_data(ttl=3600)
def get_intercompany_revenue(year, company_id=None):
    """Haal alleen intercompany omzet op voor IC filtering"""
    domain = [
        ("account_id.code", ">=", "800000"),
        ("account_id.code", "<", "900000"),
        ("date", ">=", f"{year}-01-01"),
        ("date", "<=", f"{year}-12-31"),
        ("parent_state", "=", "posted"),
        ("partner_id", "in", INTERCOMPANY_PARTNERS)
    ]
    if company_id:
        domain.append(("company_id", "=", company_id))
    
    result = odoo_read_group("account.move.line", domain, ["balance:sum"], ["date:month"])
    return result

@st.cache_data(ttl=3600)
def get_intercompany_costs(year, company_id=None):
    """Haal alleen intercompany kosten op voor IC filtering"""
    # 4* rekeningen
    domain_4 = [
        ("account_id.code", ">=", "400000"),
        ("account_id.code", "<", "500000"),
        ("date", ">=", f"{year}-01-01"),
        ("date", "<=", f"{year}-12-31"),
        ("parent_state", "=", "posted"),
        ("partner_id", "in", INTERCOMPANY_PARTNERS)
    ]
    if company_id:
        domain_4.append(("company_id", "=", company_id))
    
    # 6* rekeningen
    domain_6 = [
        ("account_id.code", ">=", "600000"),
        ("account_id.code", "<", "700000"),
        ("date", ">=", f"{year}-01-01"),
        ("date", "<=", f"{year}-12-31"),
        ("parent_state", "=", "posted"),
        ("partner_id", "in", INTERCOMPANY_PARTNERS)
    ]
    if company_id:
        domain_6.append(("company_id", "=", company_id))
    
    # 7* rekeningen
    domain_7 = [
        ("account_id.code", ">=", "700000"),
        ("account_id.code", "<", "800000"),
        ("date", ">=", f"{year}-01-01"),
        ("date", "<=", f"{year}-12-31"),
        ("parent_state", "=", "posted"),
        ("partner_id", "in", INTERCOMPANY_PARTNERS)
    ]
    if company_id:
        domain_7.append(("company_id", "=", company_id))
    
    result_4 = odoo_read_group("account.move.line", domain_4, ["balance:sum"], ["date:month"])
    result_6 = odoo_read_group("account.move.line", domain_6, ["balance:sum"], ["date:month"])
    result_7 = odoo_read_group("account.move.line", domain_7, ["balance:sum"], ["date:month"])
    
    monthly = {}
    for r in result_4 + result_6 + result_7:
        month = r.get("date:month", "Unknown")
        if month not in monthly:
            monthly[month] = 0
        monthly[month] += r.get("balance", 0)
    
    return [{"date:month": k, "balance": v} for k, v in monthly.items()]

@st.cache_data(ttl=3600)
def get_weekly_revenue(year, company_id=None, exclude_intercompany=False):
    """Haal wekelijkse omzetdata op via read_group (geen record limiet)"""
    domain = [
        ("account_id.code", ">=", "800000"),
        ("account_id.code", "<", "900000"),
        ("date", ">=", f"{year}-01-01"),
        ("date", "<=", f"{year}-12-31"),
        ("parent_state", "=", "posted")
    ]
    if company_id:
        domain.append(("company_id", "=", company_id))
    if exclude_intercompany and INTERCOMPANY_PARTNERS:
        domain.append(("partner_id", "not in", INTERCOMPANY_PARTNERS))
    
    # Groepeer op week (date:week geeft ISO weeknummer)
    result = odoo_read_group("account.move.line", domain, ["balance:sum"], ["date:week"])
    
    # Converteer naar lijst met weeknummer en omzet (omzet is negatief in Odoo)
    weekly_data = []
    import re
    from datetime import datetime
    for r in result:
        week_str = r.get("date:week", "")
        balance = -r.get("balance", 0)  # Negatief -> positief voor omzet
        if week_str and balance != 0:
            # Parse "W01 2025" of "Week 01 2025" format
            try:
                # Zoek weeknummer en jaar met regex
                match = re.search(r'W?(?:eek\s*)?(\d+)\s+(\d{4})', week_str, re.IGNORECASE)
                if match:
                    week_num = int(match.group(1))
                    week_year = int(match.group(2))
                    # Maak datum van eerste dag van de week (maandag)
                    # ISO week: gebruik isocalendar format
                    date = datetime.strptime(f"{week_year}-W{week_num:02d}-1", "%G-W%V-%u")
                    weekly_data.append({
                        "week": week_str,
                        "week_num": week_num,
                        "date": date.strftime("%Y-%m-%d"),
                        "omzet": balance
                    })
            except:
                pass
    
    # Sorteer op datum
    weekly_data.sort(key=lambda x: x.get("date", ""))
    return weekly_data

@st.cache_data(ttl=3600)
def get_daily_revenue(year, company_id=None, exclude_intercompany=False):
    """Haal dagelijkse omzetdata op via read_group (geen record limiet)"""
    domain = [
        ("account_id.code", ">=", "800000"),
        ("account_id.code", "<", "900000"),
        ("date", ">=", f"{year}-01-01"),
        ("date", "<=", f"{year}-12-31"),
        ("parent_state", "=", "posted")
    ]
    if company_id:
        domain.append(("company_id", "=", company_id))
    if exclude_intercompany and INTERCOMPANY_PARTNERS:
        domain.append(("partner_id", "not in", INTERCOMPANY_PARTNERS))
    
    # Groepeer op dag
    result = odoo_read_group("account.move.line", domain, ["balance:sum"], ["date:day"])
    
    # Converteer naar lijst met datum en omzet
    daily_data = []
    # Nederlandse maand mapping
    dutch_months = {
        'jan': '01', 'feb': '02', 'mrt': '03', 'apr': '04',
        'mei': '05', 'jun': '06', 'jul': '07', 'aug': '08',
        'sep': '09', 'okt': '10', 'nov': '11', 'dec': '12',
        # Engels als fallback
        'mar': '03', 'may': '05', 'oct': '10'
    }
    for r in result:
        date_str = r.get("date:day", "")
        balance = -r.get("balance", 0)  # Negatief -> positief voor omzet
        if date_str and balance != 0:
            try:
                # Parse "01 jan 2025" of "01 Jan 2025" format
                parts = date_str.lower().split()
                if len(parts) == 3:
                    day = parts[0].zfill(2)
                    month = dutch_months.get(parts[1][:3], "01")
                    year = parts[2]
                    iso_date = f"{year}-{month}-{day}"
                    daily_data.append({
                        "date": iso_date,
                        "dag": date_str,
                        "omzet": balance
                    })
            except:
                pass
    
    # Sorteer op datum
    daily_data.sort(key=lambda x: x.get("date", ""))
    return daily_data

# Legacy functies voor compatibiliteit (niet meer primair gebruikt)
@st.cache_data(ttl=300)
def get_revenue_data(year, company_id=None):
    """Haal omzetdata op van 8* rekeningen - LEGACY, gebruik get_revenue_aggregated"""
    domain = [
        ["account_id.code", ">=", "800000"],
        ["account_id.code", "<", "900000"],
        ["date", ">=", f"{year}-01-01"],
        ["date", "<=", f"{year}-12-31"],
        ["parent_state", "=", "posted"]
    ]
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    return odoo_call(
        "account.move.line", "search_read",
        domain,
        ["date", "account_id", "company_id", "balance", "name", "partner_id"],
        limit=100000,
        include_archived=True  # Inclusief gearchiveerde records
    )

@st.cache_data(ttl=300)
def get_cost_data(year, company_id=None):
    """Haal kostendata op van 4*, 6* en 7* rekeningen - LEGACY"""
    domain = [
        "|", "|",
        "&", ["account_id.code", ">=", "400000"], ["account_id.code", "<", "500000"],
        "&", ["account_id.code", ">=", "600000"], ["account_id.code", "<", "700000"],
        "&", ["account_id.code", ">=", "700000"], ["account_id.code", "<", "800000"],
        ["date", ">=", f"{year}-01-01"],
        ["date", "<=", f"{year}-12-31"],
        ["parent_state", "=", "posted"]
    ]
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    return odoo_call(
        "account.move.line", "search_read",
        domain,
        ["date", "account_id", "company_id", "balance", "name", "partner_id"],
        limit=100000,
        include_archived=True  # Inclusief gearchiveerde records
    )

@st.cache_data(ttl=300)
def get_receivables_payables(company_id=None):
    """Haal debiteuren en crediteuren saldi op"""
    # Debiteuren
    rec_domain = [
        ["account_id.account_type", "=", "asset_receivable"],
        ["parent_state", "=", "posted"],
        ["amount_residual", "!=", 0]
    ]
    if company_id:
        rec_domain.append(["company_id", "=", company_id])
    
    receivables = odoo_call(
        "account.move.line", "search_read",
        rec_domain,
        ["company_id", "amount_residual", "partner_id"],
        limit=5000,
        include_archived=True  # Inclusief gearchiveerde contacten
    )
    
    # Crediteuren
    pay_domain = [
        ["account_id.account_type", "=", "liability_payable"],
        ["parent_state", "=", "posted"],
        ["amount_residual", "!=", 0]
    ]
    if company_id:
        pay_domain.append(["company_id", "=", company_id])
    
    payables = odoo_call(
        "account.move.line", "search_read",
        pay_domain,
        ["company_id", "amount_residual", "partner_id"],
        limit=5000,
        include_archived=True  # Inclusief gearchiveerde contacten
    )
    
    return receivables, payables

@st.cache_data(ttl=300)
def get_receivables_by_partner(company_id=None):
    """Haal debiteuren op gegroepeerd per partner voor cashflow prognose filtering"""
    rec_domain = [
        ["account_id.account_type", "=", "asset_receivable"],
        ["parent_state", "=", "posted"],
        ["amount_residual", "!=", 0]
    ]
    if company_id:
        rec_domain.append(["company_id", "=", company_id])

    receivables = odoo_call(
        "account.move.line", "search_read",
        rec_domain,
        ["company_id", "amount_residual", "partner_id", "date_maturity", "date"],
        limit=5000,
        include_archived=True
    )

    # Groepeer per partner
    partner_totals = {}
    for r in receivables:
        partner = r.get("partner_id")
        if partner:
            partner_id = partner[0]
            partner_name = partner[1] if len(partner) > 1 else f"Partner {partner_id}"
            if partner_id not in partner_totals:
                partner_totals[partner_id] = {
                    "name": partner_name,
                    "total": 0,
                    "items": []
                }
            partner_totals[partner_id]["total"] += r.get("amount_residual", 0)
            partner_totals[partner_id]["items"].append(r)

    return partner_totals

@st.cache_data(ttl=300)
def get_payables_by_partner(company_id=None):
    """Haal crediteuren op gegroepeerd per partner voor cashflow prognose filtering"""
    pay_domain = [
        ["account_id.account_type", "=", "liability_payable"],
        ["parent_state", "=", "posted"],
        ["amount_residual", "!=", 0]
    ]
    if company_id:
        pay_domain.append(["company_id", "=", company_id])

    payables = odoo_call(
        "account.move.line", "search_read",
        pay_domain,
        ["company_id", "amount_residual", "partner_id", "date_maturity", "date"],
        limit=5000,
        include_archived=True
    )

    # Groepeer per partner
    partner_totals = {}
    for p in payables:
        partner = p.get("partner_id")
        if partner:
            partner_id = partner[0]
            partner_name = partner[1] if len(partner) > 1 else f"Partner {partner_id}"
            if partner_id not in partner_totals:
                partner_totals[partner_id] = {
                    "name": partner_name,
                    "total": 0,
                    "items": []
                }
            partner_totals[partner_id]["total"] += abs(p.get("amount_residual", 0))
            partner_totals[partner_id]["items"].append(p)

    return partner_totals

@st.cache_data(ttl=1800)  # 30 minuten cache
def get_vat_monthly_data(company_id=None, months_back=6):
    """Haal BTW-data op uit de 15* rekeningen per maand voor cashflow prognose.

    BTW accounts (15* rekeningen in Odoo):
    - 1500xx: Te vorderen BTW (voorbelasting / input VAT) - debit
    - 1510xx: Af te dragen BTW (output VAT) - credit
    - 1520xx: BTW verrekenrekening

    Returns per maand de netto BTW positie (credit - debit = af te dragen).
    """
    from datetime import datetime
    from dateutil.relativedelta import relativedelta

    today = datetime.now().date()
    start_date = (today.replace(day=1) - relativedelta(months=months_back)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    # Domain voor 15* rekeningen (BTW rekeningen)
    vat_domain = [
        ("date", ">=", start_date),
        ("date", "<=", end_date),
        ("parent_state", "=", "posted"),
        ("account_id.code", "like", "15%")  # BTW rekeningen starten met 15
    ]
    if company_id:
        vat_domain.append(("company_id", "=", company_id))

    # Groepeer per maand
    result = odoo_read_group(
        "account.move.line",
        vat_domain,
        ["debit:sum", "credit:sum"],
        ["date:month"]
    )

    # Bereken netto BTW per maand (credit - debit = af te dragen BTW)
    monthly_vat = []
    for item in result:
        debit = item.get("debit", 0) or 0
        credit = item.get("credit", 0) or 0
        net_vat = credit - debit  # Positief = af te dragen, negatief = te ontvangen
        month_label = item.get("date:month", "Onbekend")
        monthly_vat.append({
            "month": month_label,
            "debit": debit,
            "credit": credit,
            "net_vat": net_vat
        })

    return monthly_vat

@st.cache_data(ttl=300)
def get_historical_bank_movements(company_id=None, weeks_back=8):
    """Haal historische bankmutaties op per week uit de bankdagboeken"""
    from datetime import datetime, timedelta

    # Bereken startdatum (x weken terug, vanaf begin van die week)
    today = datetime.now().date()
    current_week_start = today - timedelta(days=today.weekday())
    start_date = current_week_start - timedelta(weeks=weeks_back)

    # Haal eerst de bank account IDs op
    bank_journals = get_bank_balances()
    bank_account_ids = []
    for j in bank_journals:
        acc_id = j.get("default_account_id")
        if acc_id:
            bank_account_ids.append(acc_id[0] if isinstance(acc_id, list) else acc_id)

    if not bank_account_ids:
        return {}

    # Haal alle bankmutaties op in de periode
    domain = [
        ["account_id", "in", bank_account_ids],
        ["parent_state", "=", "posted"],
        ["date", ">=", start_date.strftime("%Y-%m-%d")],
        ["date", "<", current_week_start.strftime("%Y-%m-%d")]
    ]
    if company_id:
        domain.append(["company_id", "=", company_id])

    movements = odoo_call(
        "account.move.line", "search_read",
        domain,
        ["date", "debit", "credit", "balance", "company_id", "partner_id", "name"],
        limit=10000
    )

    # Groepeer per week
    weekly_data = {}
    for m in movements:
        date_str = m.get("date")
        if date_str:
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
            week_start = date - timedelta(days=date.weekday())
            week_key = week_start.strftime("%Y-%m-%d")

            if week_key not in weekly_data:
                weekly_data[week_key] = {
                    "week_start": week_start,
                    "inflow": 0,
                    "outflow": 0,
                    "net": 0
                }

            debit = m.get("debit", 0) or 0
            credit = m.get("credit", 0) or 0

            weekly_data[week_key]["inflow"] += debit
            weekly_data[week_key]["outflow"] += credit
            weekly_data[week_key]["net"] += (debit - credit)

    return weekly_data

@st.cache_data(ttl=300)
def get_invoices(year, company_id=None, invoice_type=None, state=None, search_term=None):
    """Haal facturen op met filters"""
    domain = [
        ["invoice_date", ">=", f"{year}-01-01"],
        ["invoice_date", "<=", f"{year}-12-31"]
    ]
    
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    if invoice_type == "verkoop":
        domain.append(["move_type", "in", ["out_invoice", "out_refund"]])
    elif invoice_type == "inkoop":
        domain.append(["move_type", "in", ["in_invoice", "in_refund"]])
    else:
        domain.append(["move_type", "in", ["out_invoice", "out_refund", "in_invoice", "in_refund"]])
    
    if state:
        domain.append(["state", "=", state])
    
    if search_term:
        domain = ["&"] + domain + ["|", "|",
            ["name", "ilike", search_term],
            ["partner_id.name", "ilike", search_term],
            ["ref", "ilike", search_term]
        ]
    
    return odoo_call(
        "account.move", "search_read",
        domain,
        ["name", "partner_id", "invoice_date", "amount_total", "amount_residual", 
         "state", "move_type", "company_id", "ref"],
        limit=500,
        include_archived=True  # Inclusief gearchiveerde contacten
    )

@st.cache_data(ttl=300)
def get_product_sales(year, company_id=None):
    """Haal verkopen per productcategorie op"""
    domain = [
        ["move_id.move_type", "=", "out_invoice"],
        ["move_id.state", "=", "posted"],
        ["move_id.invoice_date", ">=", f"{year}-01-01"],
        ["move_id.invoice_date", "<=", f"{year}-12-31"],
        ["product_id", "!=", False]
    ]
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    return odoo_call(
        "account.move.line", "search_read",
        domain,
        ["product_id", "price_subtotal", "quantity", "company_id"],
        limit=10000,
        include_archived=True  # Inclusief gearchiveerde producten
    )

@st.cache_data(ttl=300)
def get_product_categories_for_ids(product_ids_tuple):
    """Haal categorieën op voor specifieke product IDs (inclusief gearchiveerde)
    
    Args:
        product_ids_tuple: tuple van product IDs (tuple voor caching)
    """
    if not product_ids_tuple:
        return {}
    
    product_ids = list(product_ids_tuple)
    
    # Haal producten op inclusief gearchiveerde
    products = odoo_call(
        "product.product", "search_read",
        [["id", "in", product_ids]],
        ["id", "name", "categ_id"],
        limit=len(product_ids) + 100,
        include_archived=True
    )
    return {p["id"]: p.get("categ_id", [None, "Onbekend"]) for p in products}

@st.cache_data(ttl=300)
def get_product_categories():
    """Backward compatibility - haalt eerste batch producten op"""
    products = odoo_call(
        "product.product", "search_read",
        [],
        ["id", "name", "categ_id"],
        limit=50000,
        include_archived=True
    )
    return {p["id"]: p.get("categ_id", [None, "Onbekend"]) for p in products}

@st.cache_data(ttl=300)
def get_pos_product_sales(year, company_id=None):
    """Haal POS verkopen op met productinfo (voor LAB Conceptstore)"""
    # Haal POS orders op voor het jaar
    domain = [
        ["state", "in", ["paid", "done", "invoiced"]],
        ["date_order", ">=", f"{year}-01-01"],
        ["date_order", "<=", f"{year}-12-31 23:59:59"]
    ]
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    orders = odoo_call(
        "pos.order", "search_read",
        domain,
        ["id", "name", "date_order", "amount_total"],
        limit=50000,
        include_archived=True
    )
    
    if not orders:
        return []
    
    order_ids = [o["id"] for o in orders]
    
    # Haal orderregels op met product en categorie
    lines = odoo_call(
        "pos.order.line", "search_read",
        [["order_id", "in", order_ids]],
        ["product_id", "price_subtotal_incl", "price_subtotal", "qty", "order_id"],
        limit=100000,
        include_archived=True
    )
    
    return lines

@st.cache_data(ttl=300)
def get_verf_behang_analysis(year):
    """Haal Verf vs Behang analyse op voor LAB Projects (company 3)
    
    Logica:
    - Arbeid (ID 735083) op factuur → Verfproject
    - Arbeid Behanger (ID 735084, 777873) op factuur → Behangproject
    - Arbeid regels = dienst omzet
    - Overige regels op zelfde factuur = materiaalkosten
    """
    ARBEID_VERF_ID = 735083
    ARBEID_BEHANG_IDS = [735084, 777873]
    
    # Haal alle factuurregels op voor LAB Projects
    lines = odoo_call(
        "account.move.line", "search_read",
        [
            ["move_id.move_type", "=", "out_invoice"],
            ["move_id.state", "=", "posted"],
            ["move_id.invoice_date", ">=", f"{year}-01-01"],
            ["move_id.invoice_date", "<=", f"{year}-12-31"],
            ["company_id", "=", 3],  # LAB Projects
            ["account_id.code", "=like", "8%"]  # Omzet rekeningen
        ],
        ["move_id", "product_id", "price_subtotal"],
        limit=50000,
        include_archived=True
    )
    
    if not lines:
        return None
    
    # Groepeer per factuur
    invoices = {}
    for line in lines:
        move_id = line["move_id"][0] if line["move_id"] else None
        if not move_id:
            continue
        if move_id not in invoices:
            invoices[move_id] = []
        invoices[move_id].append(line)
    
    # Analyseer per factuur
    verf_omzet = 0
    verf_materiaal = 0
    behang_omzet = 0
    behang_materiaal = 0
    
    for move_id, lines in invoices.items():
        # Bepaal type factuur op basis van Arbeid regels
        is_verf = False
        is_behang = False
        
        for line in lines:
            product_id = line["product_id"][0] if line["product_id"] else None
            if product_id == ARBEID_VERF_ID:
                is_verf = True
            elif product_id in ARBEID_BEHANG_IDS:
                is_behang = True
        
        # Tel omzet en materiaal
        if is_verf or is_behang:
            for line in lines:
                product_id = line["product_id"][0] if line["product_id"] else None
                amount = line.get("price_subtotal", 0) or 0
                
                if is_behang and not is_verf:  # Alleen behang
                    if product_id in ARBEID_BEHANG_IDS:
                        behang_omzet += amount
                    else:
                        behang_materiaal += amount
                elif is_verf:  # Verf (ook als beide, default naar verf)
                    if product_id == ARBEID_VERF_ID:
                        verf_omzet += amount
                    elif product_id not in ARBEID_BEHANG_IDS:
                        verf_materiaal += amount
    
    return {
        "verf": {"omzet": verf_omzet, "materiaal": verf_materiaal},
        "behang": {"omzet": behang_omzet, "materiaal": behang_materiaal}
    }

@st.cache_data(ttl=300)
def get_top_products(year, company_id=None, limit=20):
    """Haal top producten op met omzet"""
    domain = [
        ["move_id.move_type", "=", "out_invoice"],
        ["move_id.state", "=", "posted"],
        ["move_id.invoice_date", ">=", f"{year}-01-01"],
        ["move_id.invoice_date", "<=", f"{year}-12-31"],
        ["product_id", "!=", False]
    ]
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    lines = odoo_call(
        "account.move.line", "search_read",
        domain,
        ["product_id", "price_subtotal", "quantity"],
        limit=100000,
        include_archived=True
    )
    
    # Groepeer per product
    products = {}
    for line in lines:
        prod = line.get("product_id")
        if prod:
            prod_id = prod[0]
            prod_name = prod[1]
            if prod_id not in products:
                products[prod_id] = {"name": prod_name, "omzet": 0, "aantal": 0}
            products[prod_id]["omzet"] += line.get("price_subtotal", 0)
            products[prod_id]["aantal"] += line.get("quantity", 0)
    
    # Sorteer en return top N
    sorted_products = sorted(products.values(), key=lambda x: -x["omzet"])
    return sorted_products[:limit]

@st.cache_data(ttl=300)
def get_customer_locations(company_id=3):
    """Haal klantlocaties op voor LAB Projects (of andere entiteit)"""
    # Haal alle klanten met adressen op die facturen hebben gehad
    invoices = odoo_call(
        "account.move", "search_read",
        [
            ["company_id", "=", company_id],
            ["move_type", "=", "out_invoice"],
            ["state", "=", "posted"]
        ],
        ["partner_id", "amount_total"],
        limit=5000,
        include_archived=True
    )
    
    # Verzamel unieke klant IDs met omzet
    customer_revenue = {}
    for inv in invoices:
        partner = inv.get("partner_id")
        if partner:
            pid = partner[0]
            if pid not in customer_revenue:
                customer_revenue[pid] = {"name": partner[1], "omzet": 0, "facturen": 0}
            customer_revenue[pid]["omzet"] += inv.get("amount_total", 0)
            customer_revenue[pid]["facturen"] += 1
    
    if not customer_revenue:
        return []
    
    # Haal adresgegevens op
    partner_ids = list(customer_revenue.keys())
    partners = odoo_call(
        "res.partner", "search_read",
        [["id", "in", partner_ids]],
        ["id", "name", "street", "zip", "city", "country_id"],
        include_archived=True
    )
    
    # Combineer data
    result = []
    for p in partners:
        pid = p["id"]
        if pid in customer_revenue:
            result.append({
                "id": pid,
                "name": customer_revenue[pid]["name"],
                "street": p.get("street", ""),
                "zip": p.get("zip", ""),
                "city": p.get("city", ""),
                "country": p.get("country_id", ["", ""])[1] if p.get("country_id") else "",
                "omzet": customer_revenue[pid]["omzet"],
                "facturen": customer_revenue[pid]["facturen"]
            })
    
    return result

def get_invoice_lines(invoice_id):
    """Haal factuurregels op voor een specifieke factuur"""
    return odoo_call(
        "account.move.line", "search_read",
        [
            ["move_id", "=", invoice_id],
            ["display_type", "in", ["product", False]],
            ["exclude_from_invoice_tab", "=", False]
        ],
        ["product_id", "name", "quantity", "price_unit", "price_subtotal", "tax_ids"],
        include_archived=True
    )

def get_invoice_pdf(invoice_id):
    """Haal PDF bijlage op voor een factuur (indien beschikbaar)"""
    attachments = odoo_call(
        "ir.attachment", "search_read",
        [
            ["res_model", "=", "account.move"],
            ["res_id", "=", invoice_id],
            ["mimetype", "=", "application/pdf"]
        ],
        ["name", "datas"],
        include_archived=True
    )
    return attachments[0] if attachments else None

# =============================================================================
# GEOCODING HELPER (voor klantenkaart)
# =============================================================================

# Nederlandse postcodes naar lat/lon (vereenvoudigd - eerste 2 cijfers)
POSTCODE_COORDS = {
    "10": (52.3676, 4.9041),   # Amsterdam
    "11": (52.3676, 4.9041),   # Amsterdam
    "12": (52.0907, 5.1214),   # Utrecht
    "13": (52.1561, 4.4858),   # Leiden
    "14": (52.0116, 4.3571),   # Den Haag
    "15": (52.0116, 4.3571),   # Den Haag
    "16": (52.0116, 4.3571),   # Den Haag
    "17": (51.9225, 4.4792),   # Rotterdam
    "18": (51.9225, 4.4792),   # Rotterdam
    "19": (51.9225, 4.4792),   # Rotterdam
    "20": (51.9225, 4.4792),   # Rotterdam
    "21": (51.9225, 4.4792),   # Rotterdam
    "22": (51.9225, 4.4792),   # Rotterdam
    "23": (51.9225, 4.4792),   # Rotterdam
    "24": (51.9225, 4.4792),   # Rotterdam
    "25": (51.9851, 5.8987),   # Nijmegen
    "26": (51.9851, 5.8987),   # Nijmegen
    "27": (52.2215, 6.8937),   # Enschede
    "28": (52.5168, 6.0830),   # Zwolle
    "29": (52.5168, 6.0830),   # Zwolle
    "30": (52.0907, 5.1214),   # Utrecht
    "31": (52.0907, 5.1214),   # Utrecht
    "32": (52.2215, 6.0833),   # Amersfoort
    "33": (52.2215, 6.0833),   # Amersfoort
    "34": (52.0907, 5.1214),   # Utrecht
    "35": (52.1561, 4.4858),   # Hilversum
    "36": (52.0907, 5.1214),   # Utrecht
    "37": (52.2215, 6.0833),   # Amersfoort
    "38": (52.5200, 5.4700),   # Lelystad
    "39": (52.2215, 6.0833),   # Amersfoort
    "40": (51.4416, 5.4697),   # Eindhoven
    "41": (51.4416, 5.4697),   # Eindhoven
    "42": (51.4416, 5.4697),   # Eindhoven
    "43": (51.5555, 5.0913),   # Tilburg
    "44": (51.5890, 4.7756),   # Breda
    "45": (51.5890, 4.7756),   # Breda
    "46": (51.5890, 4.7756),   # Breda
    "47": (51.5890, 4.7756),   # Breda
    "48": (51.4416, 5.4697),   # Eindhoven
    "49": (51.5555, 5.0913),   # Tilburg
    "50": (51.4416, 5.4697),   # Eindhoven
    "51": (51.4416, 5.4697),   # Eindhoven
    "52": (51.4416, 5.4697),   # Eindhoven
    "53": (51.4416, 5.4697),   # Eindhoven
    "54": (51.4416, 5.4697),   # Eindhoven
    "55": (51.4416, 5.4697),   # Eindhoven
    "56": (51.4416, 5.4697),   # Eindhoven
    "57": (51.4416, 5.4697),   # Eindhoven
    "58": (51.4416, 5.4697),   # Eindhoven
    "59": (51.5555, 5.0913),   # Tilburg
    "60": (50.8514, 5.6910),   # Maastricht
    "61": (50.8514, 5.6910),   # Maastricht
    "62": (50.8514, 5.6910),   # Maastricht
    "63": (50.8514, 5.6910),   # Maastricht
    "64": (50.8514, 5.6910),   # Maastricht
    "65": (51.4427, 6.0608),   # Roermond
    "66": (51.4427, 6.0608),   # Roermond
    "67": (51.9851, 5.8987),   # Nijmegen
    "68": (51.9851, 5.8987),   # Nijmegen
    "69": (51.9225, 6.0833),   # Arnhem
    "70": (51.9225, 6.0833),   # Arnhem
    "71": (51.9851, 5.8987),   # Nijmegen
    "72": (52.0116, 6.0833),   # Apeldoorn
    "73": (52.0116, 6.0833),   # Apeldoorn
    "74": (52.0116, 6.0833),   # Apeldoorn
    "75": (52.2215, 6.8937),   # Enschede
    "76": (52.2215, 6.8937),   # Enschede
    "77": (52.2215, 6.8937),   # Enschede
    "78": (52.5168, 6.0830),   # Zwolle
    "79": (52.5168, 6.0830),   # Zwolle
    "80": (52.5168, 6.0830),   # Zwolle
    "81": (52.5168, 6.0830),   # Zwolle
    "82": (52.7792, 6.9004),   # Emmen
    "83": (52.7792, 6.9004),   # Emmen
    "84": (53.2194, 6.5665),   # Groningen
    "85": (53.2194, 6.5665),   # Groningen
    "86": (53.2194, 6.5665),   # Groningen
    "87": (53.2194, 6.5665),   # Groningen
    "88": (53.0000, 5.7500),   # Leeuwarden
    "89": (53.0000, 5.7500),   # Leeuwarden
    "90": (53.0000, 5.7500),   # Leeuwarden
    "91": (53.0000, 5.7500),   # Leeuwarden
    "92": (53.0000, 5.7500),   # Leeuwarden
    "93": (53.2194, 6.5665),   # Groningen
    "94": (53.2194, 6.5665),   # Groningen
    "95": (53.2194, 6.5665),   # Groningen
    "96": (53.2194, 6.5665),   # Groningen
    "97": (53.2194, 6.5665),   # Groningen
    "98": (53.2194, 6.5665),   # Groningen
    "99": (53.2194, 6.5665),   # Groningen
}

def get_coords_from_postcode(postcode):
    """Haal lat/lon op basis van postcode (eerste 2 cijfers)"""
    if not postcode:
        return None, None
    prefix = str(postcode).strip()[:2]
    if prefix in POSTCODE_COORDS:
        return POSTCODE_COORDS[prefix]
    return None, None

# =============================================================================
# MAIN APP
# =============================================================================

def main():
    st.title("📊 LAB Groep Financial Dashboard")
    st.caption("Real-time data uit Odoo | v12 - Met Maandafsluiting (Financial Close)")
    
    # Sidebar
    st.sidebar.header("🔧 Filters")
    
    # API Key input (alleen tonen als niet in secrets)
    api_from_secrets = False
    try:
        if st.secrets.get("ODOO_API_KEY", ""):
            api_from_secrets = True
    except:
        pass
    
    if not api_from_secrets:
        st.sidebar.markdown("### 🔑 API Configuratie")
        api_input = st.sidebar.text_input(
            "Odoo API Key", 
            value=st.session_state.get("api_key", ""),
            type="password",
            help="Voer je Odoo API key in",
            key="api_key_input"
        )
        if api_input:
            st.session_state.api_key = api_input
        st.sidebar.markdown("---")
    
    # OpenAI API Key voor chatbot
    st.sidebar.markdown("### 🤖 AI Chat")
    openai_input = st.sidebar.text_input(
        "OpenAI API Key",
        value=st.session_state.get("openai_key", ""),
        type="password",
        help="Voer je OpenAI API key in voor de AI Chat functie",
        key="openai_key_input"
    )
    if openai_input:
        st.session_state.openai_key = openai_input
    st.sidebar.markdown("---")
    
    # Check of we een API key hebben
    if not get_api_key():
        st.warning("👈 Voer je Odoo API Key in via de sidebar om te beginnen")
        st.stop()
    
    # Dynamische jaarlijst
    current_year = datetime.now().year
    years = list(range(current_year, 2022, -1))
    selected_year = st.sidebar.selectbox("📅 Jaar", years, index=0)
    
    # Entiteit selectie
    entity_options = ["Alle bedrijven"] + list(COMPANIES.values())
    selected_entity = st.sidebar.selectbox("🏢 Entiteit", entity_options)
    
    company_id = None
    if selected_entity != "Alle bedrijven":
        company_id = [k for k, v in COMPANIES.items() if v == selected_entity][0]
    
    # Intercompany filter (beschikbaar voor alle entiteiten)
    # Gebruik session_state om de waarde te behouden bij jaar/entiteit wijzigingen
    st.sidebar.markdown("---")
    if "exclude_intercompany" not in st.session_state:
        st.session_state.exclude_intercompany = False
    
    exclude_intercompany = st.sidebar.checkbox(
        "🔄 Intercompany uitsluiten",
        value=st.session_state.exclude_intercompany,
        key="exclude_intercompany_checkbox",
        help="Sluit boekingen met andere LAB-entiteiten uit (bijv. facturen tussen LAB Shops en LAB Projects)"
    )
    st.session_state.exclude_intercompany = exclude_intercompany
    
    st.sidebar.markdown("---")
    st.sidebar.caption(f"⏱️ Laatste update: {datetime.now().strftime('%H:%M:%S')}")
    if st.sidebar.button("🔄 Ververs data"):
        st.cache_data.clear()
        st.rerun()
    
    # ==========================================================================
    # TABS
    # ==========================================================================
    tabs = st.tabs(["💳 Overzicht", "🏦 Bank", "📄 Facturen", "🏆 Producten", "🗺️ Klantenkaart", "📉 Kosten", "📈 Cashflow", "📊 Balans", "💬 AI Chat", "📋 Maandafsluiting"])
    
    # =========================================================================
    # TAB 1: OVERZICHT
    # =========================================================================
    with tabs[0]:
        st.header("📊 Financieel Overzicht")
        
        # KPIs
        col1, col2, col3, col4 = st.columns(4)
        
        with st.spinner("Data laden via server-side aggregatie..."):
            # Gebruik read_group voor snelle server-side aggregatie (geen record limiet!)
            revenue_agg = get_revenue_aggregated(selected_year, company_id)
            cost_agg = get_cost_aggregated(selected_year, company_id)
            bank_data = get_bank_balances()
            receivables, payables = get_receivables_payables(company_id)
        
        # Bereken totalen uit geaggregeerde data
        total_revenue_raw = -sum(r.get("balance", 0) for r in revenue_agg)
        total_costs_raw = sum(c.get("balance", 0) for c in cost_agg)
        
        # Filter intercompany indien geselecteerd
        if exclude_intercompany:
            # Haal IC-bedragen apart op en trek af
            with st.spinner("Intercompany filtering..."):
                ic_revenue = get_intercompany_revenue(selected_year, company_id)
                ic_costs = get_intercompany_costs(selected_year, company_id)
            ic_revenue_total = -sum(r.get("balance", 0) for r in ic_revenue)
            ic_costs_total = sum(c.get("balance", 0) for c in ic_costs)
            total_revenue = total_revenue_raw - ic_revenue_total
            total_costs = total_costs_raw - ic_costs_total
        else:
            total_revenue = total_revenue_raw
            total_costs = total_costs_raw
        
        result = total_revenue - total_costs
        
        # Filter bank voor geselecteerde company
        if company_id:
            bank_total = sum(b.get("current_statement_balance", 0) for b in bank_data 
                          if b.get("company_id", [None])[0] == company_id)
        else:
            bank_total = sum(b.get("current_statement_balance", 0) for b in bank_data)
        
        ic_suffix = " (excl. IC)" if exclude_intercompany else ""
        with col1:
            st.metric(f"💰 Omzet YTD{ic_suffix}", f"€{total_revenue:,.0f}")
        with col2:
            st.metric(f"📉 Kosten YTD{ic_suffix}", f"€{total_costs:,.0f}")
        with col3:
            st.metric("📊 Resultaat", f"€{result:,.0f}", 
                     delta=f"{result/total_revenue*100:.1f}%" if total_revenue else "0%")
        with col4:
            st.metric("🏦 Banksaldo", f"€{bank_total:,.0f}")
        
        # Debiteuren/Crediteuren
        st.markdown("---")
        col1, col2 = st.columns(2)
        
        rec_total = sum(r.get("amount_residual", 0) for r in receivables)
        pay_total = sum(p.get("amount_residual", 0) for p in payables)
        
        with col1:
            st.metric("👥 Debiteuren", f"€{rec_total:,.0f}")
        with col2:
            st.metric("🏭 Crediteuren", f"€{abs(pay_total):,.0f}")
        
        # Omzet vs Kosten grafiek
        st.markdown("---")
        chart_title = "📈 Omzet vs Kosten per maand" + (" (excl. IC)" if exclude_intercompany else "")
        st.subheader(chart_title)
        
        # Helper functie om maandnaam naar sorteerbare datum te converteren
        def parse_month_key(month_str):
            """Converteer 'January 2025' naar '2025-01' voor sortering"""
            month_map = {
                'January': '01', 'February': '02', 'March': '03', 'April': '04',
                'May': '05', 'June': '06', 'July': '07', 'August': '08',
                'September': '09', 'October': '10', 'November': '11', 'December': '12',
                # Nederlandse maanden
                'januari': '01', 'februari': '02', 'maart': '03', 'april': '04',
                'mei': '05', 'juni': '06', 'juli': '07', 'augustus': '08',
                'september': '09', 'oktober': '10', 'november': '11', 'december': '12'
            }
            try:
                parts = month_str.split()
                if len(parts) == 2:
                    month_name, year = parts
                    month_num = month_map.get(month_name, '00')
                    return f"{year}-{month_num}"
                return month_str
            except:
                return month_str
        
        # Bouw monthly data van geaggregeerde resultaten
        if revenue_agg:
            monthly = {}
            
            # Omzet per maand
            for r in revenue_agg:
                month_raw = r.get("date:month", "Unknown")
                month = parse_month_key(month_raw)
                if month not in monthly:
                    monthly[month] = {"omzet": 0, "kosten": 0}
                monthly[month]["omzet"] += -r.get("balance", 0)
            
            # Kosten per maand
            for c in cost_agg:
                month_raw = c.get("date:month", "Unknown")
                month = parse_month_key(month_raw)
                if month not in monthly:
                    monthly[month] = {"omzet": 0, "kosten": 0}
                monthly[month]["kosten"] += c.get("balance", 0)
            
            # Als IC filter aan: trek IC bedragen af per maand
            if exclude_intercompany:
                ic_revenue = get_intercompany_revenue(selected_year, company_id)
                ic_costs = get_intercompany_costs(selected_year, company_id)
                
                for r in ic_revenue:
                    month_raw = r.get("date:month", "Unknown")
                    month = parse_month_key(month_raw)
                    if month in monthly:
                        monthly[month]["omzet"] -= -r.get("balance", 0)
                
                for c in ic_costs:
                    month_raw = c.get("date:month", "Unknown")
                    month = parse_month_key(month_raw)
                    if month in monthly:
                        monthly[month]["kosten"] -= c.get("balance", 0)
            
            df_monthly = pd.DataFrame([
                {"Maand": k, "Omzet": v["omzet"], "Kosten": v["kosten"]}
                for k, v in sorted(monthly.items())
            ])
            
            if not df_monthly.empty:
                fig = go.Figure()
                fig.add_trace(go.Bar(name="Omzet", x=df_monthly["Maand"], y=df_monthly["Omzet"],
                                    marker_color="#1e3a5f"))
                fig.add_trace(go.Bar(name="Kosten", x=df_monthly["Maand"], y=df_monthly["Kosten"],
                                    marker_color="#87CEEB"))
                fig.update_layout(barmode="group", height=400)
                st.plotly_chart(fig, use_container_width=True)
        
        # =====================================================================
        # OMZET GRAFIEK MET INTERACTIEVE SLIDER (WEEK/DAG TOGGLE)
        # =====================================================================
        st.markdown("---")
        st.subheader("📊 Omzet Tijdlijn" + (" (excl. IC)" if exclude_intercompany else ""))
        
        # Toggle voor week/dag weergave
        view_col1, view_col2 = st.columns([1, 4])
        with view_col1:
            time_view = st.radio(
                "Weergave",
                ["📅 Week", "📆 Dag"],
                horizontal=True,
                label_visibility="collapsed"
            )
        with view_col2:
            st.caption("💡 Kies 'Dag' voor detail • Gebruik de schuifbalk om te navigeren • Sleep de randen om in te zoomen")
        
        if time_view == "📅 Week":
            # WEEKWEERGAVE
            weekly_data = get_weekly_revenue(selected_year, company_id, exclude_intercompany)
            
            if weekly_data:
                df_weekly = pd.DataFrame(weekly_data)
                
                fig_weekly = go.Figure()
                
                fig_weekly.add_trace(go.Bar(
                    x=df_weekly["date"],
                    y=df_weekly["omzet"],
                    name="Weekomzet",
                    marker_color="#1e3a5f",
                    hovertemplate="<b>Week %{customdata}</b><br>Omzet: €%{y:,.0f}<extra></extra>",
                    customdata=df_weekly["week_num"]
                ))
                
                # Trendlijn (4-weeks voortschrijdend gemiddelde)
                fig_weekly.add_trace(go.Scatter(
                    x=df_weekly["date"],
                    y=df_weekly["omzet"].rolling(window=4, min_periods=1).mean(),
                    name="4-weeks gemiddelde",
                    line=dict(color="#FF6B6B", width=2, dash="dash"),
                    hovertemplate="Gemiddelde: €%{y:,.0f}<extra></extra>"
                ))
                
                fig_weekly.update_layout(
                    height=500,
                    xaxis=dict(
                        title="",
                        rangeslider=dict(
                            visible=True,
                            thickness=0.08,
                            bgcolor="#f0f2f6"
                        ),
                        type="date",
                        tickformat="Week %W<br>%b",
                        dtick="M1",  # Eén tick per maand
                        ticklabelmode="period",
                        range=[df_weekly["date"].min(), df_weekly["date"].max()],  # Toon hele jaar
                    ),
                    yaxis=dict(
                        title="Omzet (€)",
                        tickformat=",.0f",
                        gridcolor="#e0e0e0"
                    ),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    ),
                    hovermode="x unified",
                    plot_bgcolor="white",
                    margin=dict(b=80)
                )
                
                st.plotly_chart(fig_weekly, use_container_width=True)
                
                # Statistieken
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("📈 Totaal", f"€{df_weekly['omzet'].sum():,.0f}")
                with col2:
                    st.metric("📊 Gemiddeld/week", f"€{df_weekly['omzet'].mean():,.0f}")
                with col3:
                    best_week = df_weekly.loc[df_weekly['omzet'].idxmax()]
                    st.metric("🔝 Beste week", f"€{best_week['omzet']:,.0f}", f"Week {best_week['week_num']}")
                with col4:
                    worst_week = df_weekly.loc[df_weekly['omzet'].idxmin()]
                    st.metric("📉 Laagste week", f"€{worst_week['omzet']:,.0f}", f"Week {worst_week['week_num']}")
            else:
                st.info("Geen weekdata beschikbaar voor geselecteerde periode")
        
        else:
            # DAGWEERGAVE
            daily_data = get_daily_revenue(selected_year, company_id, exclude_intercompany)
            
            if daily_data:
                df_daily = pd.DataFrame(daily_data)
                
                fig_daily = go.Figure()
                
                fig_daily.add_trace(go.Bar(
                    x=df_daily["date"],
                    y=df_daily["omzet"],
                    name="Dagomzet",
                    marker_color="#2ecc71",
                    hovertemplate="<b>%{x|%a %d %b}</b><br>Omzet: €%{y:,.0f}<extra></extra>"
                ))
                
                # Trendlijn (7-daags voortschrijdend gemiddelde)
                fig_daily.add_trace(go.Scatter(
                    x=df_daily["date"],
                    y=df_daily["omzet"].rolling(window=7, min_periods=1).mean(),
                    name="7-daags gemiddelde",
                    line=dict(color="#e74c3c", width=2, dash="dash"),
                    hovertemplate="Gemiddelde: €%{y:,.0f}<extra></extra>"
                ))
                
                fig_daily.update_layout(
                    height=500,
                    xaxis=dict(
                        title="",
                        rangeslider=dict(
                            visible=True,
                            thickness=0.08,
                            bgcolor="#f0f2f6"
                        ),
                        type="date",
                        tickformat="%d %b",
                        range=[df_daily["date"].min(), df_daily["date"].max()],  # Toon hele jaar
                    ),
                    yaxis=dict(
                        title="Omzet (€)",
                        tickformat=",.0f",
                        gridcolor="#e0e0e0"
                    ),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    ),
                    hovermode="x unified",
                    plot_bgcolor="white",
                    margin=dict(b=80)
                )
                
                st.plotly_chart(fig_daily, use_container_width=True)
                
                # Statistieken
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("📈 Totaal", f"€{df_daily['omzet'].sum():,.0f}")
                with col2:
                    st.metric("📊 Gemiddeld/dag", f"€{df_daily['omzet'].mean():,.0f}")
                with col3:
                    best_day = df_daily.loc[df_daily['omzet'].idxmax()]
                    st.metric("🔝 Beste dag", f"€{best_day['omzet']:,.0f}", best_day['dag'])
                with col4:
                    st.metric("📅 Aantal dagen", f"{len(df_daily)}")
            else:
                st.info("Geen dagdata beschikbaar voor geselecteerde periode")
    
    # =========================================================================
    # TAB 2: BANK
    # =========================================================================
    with tabs[1]:
        st.header("🏦 Banksaldi per Rekening")
        
        bank_data = get_bank_balances()
        rc_data = get_rc_balances()
        
        # Filter op geselecteerde entiteit
        if selected_entity != "Alle bedrijven":
            bank_data_filtered = [b for b in bank_data if b.get("company_id", [None])[0] == company_id]
            rc_data_filtered = [r for r in rc_data if r.get("company_id", [None])[0] == company_id] if rc_data else []
            companies_to_show = {company_id: COMPANIES[company_id]}
        else:
            bank_data_filtered = bank_data
            rc_data_filtered = rc_data
            companies_to_show = COMPANIES
        
        if bank_data_filtered:
            # Totaal
            total_bank = sum(b.get("current_statement_balance", 0) for b in bank_data_filtered)
            entity_label = COMPANIES.get(company_id, "Alle Entiteiten") if selected_entity != "Alle bedrijven" else "Alle Entiteiten"
            st.metric(f"💰 Banksaldo {entity_label}", f"€{total_bank:,.0f}")
            
            # Per bedrijf
            st.markdown("---")
            
            for comp_id, comp_name in companies_to_show.items():
                comp_banks = [b for b in bank_data_filtered if b.get("company_id", [None])[0] == comp_id]
                if comp_banks:
                    comp_total = sum(b.get("current_statement_balance", 0) for b in comp_banks)
                    with st.expander(f"🏢 {comp_name} — €{comp_total:,.0f}", expanded=True):
                        for bank in comp_banks:
                            name = translate_account_name(bank.get("name", "Onbekend"))
                            balance = bank.get("current_statement_balance", 0)
                            st.write(f"  • {name}: **€{balance:,.0f}**")
            
            # R/C Intercompany sectie
            if rc_data_filtered:
                st.markdown("---")
                st.subheader("🔄 R/C Intercompany Posities")
                st.info("💡 Dit zijn rekening-courant posities met groepsmaatschappijen, geen bankrekeningen. "
                       "Rekeningen in de **12xxx** reeks zijn vorderingen, **14xxx** zijn schulden.")
                
                for comp_id, comp_name in companies_to_show.items():
                    comp_rc = [r for r in rc_data_filtered if r.get("company_id", [None])[0] == comp_id]
                    if comp_rc:
                        comp_total = sum(r.get("current_statement_balance", 0) for r in comp_rc)
                        label = "Netto vordering" if comp_total >= 0 else "Netto schuld"
                        with st.expander(f"🏢 {comp_name} — {label}: €{abs(comp_total):,.0f}"):
                            for rc in comp_rc:
                                name = translate_account_name(rc.get("name", "Onbekend"))
                                balance = rc.get("current_statement_balance", 0)
                                code = rc.get("account_code", "")
                                acc_type = rc.get("account_type", "")
                                indicator = "📈" if acc_type == "Vordering" else "📉"
                                st.write(f"  {indicator} {name} ({code}): **€{balance:,.0f}** ({acc_type})")
            
            # Grafiek - alleen tonen als "Alle bedrijven" is geselecteerd
            if selected_entity == "Alle bedrijven":
                st.markdown("---")
                st.subheader("📊 Verdeling per Entiteit")
                
                comp_totals = []
                for comp_id, comp_name in COMPANIES.items():
                    comp_total = sum(b.get("current_statement_balance", 0) for b in bank_data 
                                   if b.get("company_id", [None])[0] == comp_id)
                    if comp_total > 0:
                        comp_totals.append({"Entiteit": comp_name, "Saldo": comp_total})
                
                if comp_totals:
                    df_bank = pd.DataFrame(comp_totals)
                    fig = px.pie(df_bank, values="Saldo", names="Entiteit",
                               color_discrete_sequence=["#1e3a5f", "#4682B4", "#87CEEB"])
                    st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Geen bankgegevens beschikbaar voor deze entiteit")
    
    # =========================================================================
    # TAB 3: FACTUREN
    # =========================================================================
    with tabs[2]:
        st.header("📄 Facturen")
        
        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            inv_type = st.selectbox("Type", ["Alle", "Verkoop", "Inkoop"], key="inv_type")
            inv_type_filter = None if inv_type == "Alle" else inv_type.lower()
        with col2:
            inv_state = st.selectbox("Status", ["Alle", "Geboekt", "Concept"], key="inv_state")
            state_filter = None
            if inv_state == "Geboekt":
                state_filter = "posted"
            elif inv_state == "Concept":
                state_filter = "draft"
        with col3:
            search = st.text_input("🔍 Zoeken (nummer/klant/referentie)", key="inv_search")
        
        invoices = get_invoices(selected_year, company_id, inv_type_filter, state_filter, 
                               search if search else None)
        
        if invoices:
            st.write(f"📋 {len(invoices)} facturen gevonden")
            
            # Maak DataFrame
            df_inv = pd.DataFrame([
                {
                    "ID": inv["id"],
                    "Nummer": inv.get("name", ""),
                    "Klant/Leverancier": inv.get("partner_id", ["", ""])[1] if inv.get("partner_id") else "",
                    "Datum": inv.get("invoice_date", ""),
                    "Bedrag": inv.get("amount_total", 0),
                    "Openstaand": inv.get("amount_residual", 0),
                    "Status": "Geboekt" if inv.get("state") == "posted" else "Concept",
                    "Type": "Verkoop" if inv.get("move_type", "").startswith("out") else "Inkoop",
                    "Bedrijf": COMPANIES.get(inv.get("company_id", [None])[0], "")
                }
                for inv in invoices
            ])
            
            # Toon tabel
            st.dataframe(
                df_inv[["Nummer", "Klant/Leverancier", "Datum", "Bedrag", "Openstaand", "Status", "Type", "Bedrijf"]].style.format({
                    "Bedrag": "€{:,.2f}",
                    "Openstaand": "€{:,.2f}"
                }),
                use_container_width=True,
                hide_index=True
            )
            
            # Detail sectie
            st.markdown("---")
            st.subheader("🔍 Factuurdetails")
            
            selected_inv_num = st.selectbox(
                "Selecteer factuur voor details",
                [""] + df_inv["Nummer"].tolist(),
                key="selected_inv"
            )
            
            if selected_inv_num:
                selected_inv = next((inv for inv in invoices if inv.get("name") == selected_inv_num), None)
                if selected_inv:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown("**Factuurgegevens:**")
                        st.write(f"• Nummer: {selected_inv.get('name')}")
                        st.write(f"• Klant: {selected_inv.get('partner_id', ['',''])[1]}")
                        st.write(f"• Datum: {selected_inv.get('invoice_date')}")
                        st.write(f"• Totaal: €{selected_inv.get('amount_total', 0):,.2f}")
                        st.write(f"• Openstaand: €{selected_inv.get('amount_residual', 0):,.2f}")
                    
                    with col2:
                        # PDF download of Odoo link
                        pdf = get_invoice_pdf(selected_inv["id"])
                        if pdf and pdf.get("datas"):
                            st.download_button(
                                "📥 Download PDF",
                                data=base64.b64decode(pdf["datas"]),
                                file_name=pdf["name"],
                                mime="application/pdf"
                            )
                        else:
                            st.info("Geen PDF bijlage beschikbaar")
                        
                        odoo_url = f"https://lab.odoo.works/web#id={selected_inv['id']}&model=account.move&view_type=form"
                        st.link_button("🔗 Open in Odoo", odoo_url)
                    
                    # Factuurregels
                    st.markdown("**Factuurregels:**")
                    lines = get_invoice_lines(selected_inv["id"])
                    if lines:
                        df_lines = pd.DataFrame([
                            {
                                "Product": translate_account_name(l.get("product_id", ["", ""])[1]) if l.get("product_id") else l.get("name", ""),
                                "Omschrijving": l.get("name", ""),
                                "Aantal": l.get("quantity", 0),
                                "Prijs": l.get("price_unit", 0),
                                "Subtotaal": l.get("price_subtotal", 0)
                            }
                            for l in lines if l.get("price_subtotal", 0) != 0
                        ])
                        if not df_lines.empty:
                            st.dataframe(
                                df_lines.style.format({
                                    "Aantal": "{:.2f}",
                                    "Prijs": "€{:,.2f}",
                                    "Subtotaal": "€{:,.2f}"
                                }),
                                use_container_width=True,
                                hide_index=True
                            )
                    else:
                        st.info("Geen factuurregels beschikbaar")
        else:
            st.info("Geen facturen gevonden. Pas de filters aan.")
    
    # =========================================================================
    # TAB 4: PRODUCTEN (met subtabs)
    # =========================================================================
    with tabs[3]:
        st.header("🏆 Productanalyse")
        
        # Subtabs voor producten
        prod_subtabs = st.tabs(["📦 Productcategorieën", "🏅 Top Producten", "🎨 Verf vs Behang"])
        
        # Subtab 1: Productcategorieën
        with prod_subtabs[0]:
            st.subheader("📦 Omzet per Productcategorie")
            
            # LAB Conceptstore (ID 1) gebruikt POS data, anderen account.move.line
            is_conceptstore = company_id == 1
            
            if is_conceptstore:
                st.caption("📍 Data uit POS orders (Conceptstore)")
                pos_sales = get_pos_product_sales(selected_year, company_id)
                product_sales = pos_sales  # Voor compatibiliteit
            else:
                product_sales = get_product_sales(selected_year, company_id)
            
            # Verzamel product IDs en haal categorieën on-demand op
            product_cats = {}
            if product_sales:
                product_ids = tuple(set(p.get("product_id", [None])[0] for p in product_sales if p.get("product_id")))
                if product_ids:
                    product_cats = get_product_categories_for_ids(product_ids)
            
            if product_sales:
                # Groepeer per categorie
                cat_data = {}
                for p in product_sales:
                    prod = p.get("product_id")
                    if prod:
                        prod_id = prod[0]
                        cat = product_cats.get(prod_id, [None, "Onbekend"])
                        cat_name = cat[1] if cat else "Onbekend"
                        if cat_name not in cat_data:
                            cat_data[cat_name] = {"Omzet": 0, "Aantal": 0}
                        # POS gebruikt qty, account.move.line gebruikt quantity
                        qty_field = "qty" if is_conceptstore else "quantity"
                        cat_data[cat_name]["Omzet"] += p.get("price_subtotal", 0)
                        cat_data[cat_name]["Aantal"] += p.get(qty_field, 0)
                
                df_cat = pd.DataFrame([
                    {"Categorie": k, "Omzet": v["Omzet"], "Aantal": v["Aantal"]}
                    for k, v in sorted(cat_data.items(), key=lambda x: -x[1]["Omzet"])
                ])
                
                if not df_cat.empty:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        fig = px.bar(df_cat.head(10), x="Categorie", y="Omzet",
                                    color_discrete_sequence=["#1e3a5f"])
                        fig.update_layout(xaxis_tickangle=-45, height=400)
                        st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        fig2 = px.pie(df_cat.head(8), values="Omzet", names="Categorie",
                                     color_discrete_sequence=px.colors.sequential.Blues_r)
                        st.plotly_chart(fig2, use_container_width=True)
                    
                    st.dataframe(
                        df_cat.head(15).style.format({"Omzet": "€{:,.0f}", "Aantal": "{:,.0f}"}),
                        use_container_width=True, hide_index=True
                    )
                else:
                    st.info("Geen productcategorie data beschikbaar")
            else:
                st.info("Geen productverkopen gevonden voor deze selectie")
        
        # Subtab 2: Top Producten
        with prod_subtabs[1]:
            st.subheader("🏅 Top 20 Producten")
            
            # LAB Conceptstore gebruikt POS data
            is_conceptstore = company_id == 1
            
            if is_conceptstore:
                st.caption("📍 Data uit POS orders (Conceptstore)")
                pos_sales = get_pos_product_sales(selected_year, company_id)
                
                if pos_sales:
                    # Aggregeer POS data per product
                    prod_data = {}
                    for p in pos_sales:
                        prod = p.get("product_id")
                        if prod:
                            prod_name = prod[1]
                            if prod_name not in prod_data:
                                prod_data[prod_name] = {"Omzet": 0, "Aantal": 0}
                            prod_data[prod_name]["Omzet"] += p.get("price_subtotal", 0)
                            prod_data[prod_name]["Aantal"] += p.get("qty", 0)
                    
                    top_list = sorted(prod_data.items(), key=lambda x: -x[1]["Omzet"])[:20]
                    df_top = pd.DataFrame([
                        {"Product": k, "Omzet": v["Omzet"], "Aantal": v["Aantal"]}
                        for k, v in top_list
                    ])
                else:
                    df_top = pd.DataFrame()
            else:
                top_products = get_top_products(selected_year, company_id, limit=20)
                if top_products:
                    df_top = pd.DataFrame(top_products)
                    df_top.columns = ["Product", "Omzet", "Aantal"]
                else:
                    df_top = pd.DataFrame()
            
            if not df_top.empty:
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    fig = px.bar(df_top, y="Product", x="Omzet", orientation="h",
                                color_discrete_sequence=["#1e3a5f"])
                    fig.update_layout(height=600, yaxis={'categoryorder': 'total ascending'})
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.dataframe(
                        df_top.style.format({"Omzet": "€{:,.0f}", "Aantal": "{:,.0f}"}),
                        use_container_width=True, hide_index=True
                    )
            else:
                st.info("Geen productdata beschikbaar")
        
        # Subtab 3: Verf vs Behang (alleen relevant voor Projects)
        with prod_subtabs[2]:
            if not company_id or company_id == 3:
                st.subheader(f"🎨 LAB Projects: Verf vs Behang Analyse {selected_year}")
                
                with st.spinner("Verf vs Behang data ophalen..."):
                    vb_data = get_verf_behang_analysis(selected_year)
                
                if vb_data:
                    verf_omzet = vb_data["verf"]["omzet"]
                    verf_materiaal = vb_data["verf"]["materiaal"]
                    behang_omzet = vb_data["behang"]["omzet"]
                    behang_materiaal = vb_data["behang"]["materiaal"]
                    
                    # Bereken marge (omzet - materiaal)
                    verf_marge = verf_omzet - verf_materiaal
                    behang_marge = behang_omzet - behang_materiaal
                    
                    # Bereken percentages
                    totaal_omzet = verf_omzet + behang_omzet
                    verf_pct = (verf_omzet / totaal_omzet * 100) if totaal_omzet > 0 else 0
                    behang_pct = (behang_omzet / totaal_omzet * 100) if totaal_omzet > 0 else 0
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown(f"### 🖌️ Verfprojecten ({verf_pct:.1f}%)")
                        st.metric("Omzet (arbeid)", f"€{verf_omzet:,.0f}")
                        st.metric("Materiaalkosten", f"€{verf_materiaal:,.0f}")
                        if verf_omzet > 0:
                            st.metric("Bruto Marge", f"€{verf_marge:,.0f}", 
                                     delta=f"{verf_marge/verf_omzet*100:.1f}%")
                        else:
                            st.metric("Bruto Marge", "€0")
                    
                    with col2:
                        st.markdown(f"### 🎭 Behangprojecten ({behang_pct:.1f}%)")
                        st.metric("Omzet (arbeid)", f"€{behang_omzet:,.0f}")
                        st.metric("Materiaalkosten", f"€{behang_materiaal:,.0f}")
                        if behang_omzet > 0:
                            st.metric("Bruto Marge", f"€{behang_marge:,.0f}", 
                                     delta=f"{behang_marge/behang_omzet*100:.1f}%")
                        else:
                            st.metric("Bruto Marge", "€0")
                    
                    st.info("ℹ️ **Toelichting:** Arbeid = omzet op factuur met product 'Arbeid' of 'Arbeid Behanger'. "
                           "Materiaal = overige regels op dezelfde factuur. Onderaannemers niet beschikbaar (vereist leverancier-tagging).")
                    
                    # Vergelijkingsgrafiek
                    st.markdown("---")
                    fig = go.Figure()
                    
                    categories = ["Omzet", "Materiaal", "Marge"]
                    verf_values = [verf_omzet, verf_materiaal, verf_marge]
                    behang_values = [behang_omzet, behang_materiaal, behang_marge]
                    
                    fig.add_trace(go.Bar(name="Verf", x=categories, y=verf_values, marker_color="#1e3a5f"))
                    fig.add_trace(go.Bar(name="Behang", x=categories, y=behang_values, marker_color="#4682B4"))
                    
                    fig.update_layout(barmode="group", height=400, title=f"Vergelijking Verf vs Behang - {selected_year}")
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.warning("⚠️ Geen Verf/Behang data gevonden voor dit jaar.")
            else:
                st.info("ℹ️ De Verf vs Behang analyse is alleen beschikbaar voor LAB Projects. "
                       "Selecteer 'LAB Projects' of 'Alle bedrijven' in de sidebar.")
    
    # =========================================================================
    # TAB 5: KLANTENKAART (nieuw!)
    # =========================================================================
    with tabs[4]:
        st.header("🗺️ Klantenkaart LAB Projects")
        
        if not company_id or company_id == 3:
            with st.spinner("Klantlocaties laden..."):
                customers = get_customer_locations(3)
            
            if customers:
                st.write(f"📍 {len(customers)} klanten gevonden")
                
                # Voeg coördinaten toe
                map_data = []
                missing_coords = 0
                
                for c in customers:
                    lat, lon = get_coords_from_postcode(c.get("zip"))
                    if lat and lon:
                        # Voeg kleine random offset toe om overlapping te voorkomen
                        import random
                        lat += random.uniform(-0.02, 0.02)
                        lon += random.uniform(-0.02, 0.02)
                        
                        map_data.append({
                            "Klant": c["name"],
                            "Stad": c.get("city", ""),
                            "Postcode": c.get("zip", ""),
                            "Omzet": c["omzet"],
                            "Facturen": c["facturen"],
                            "lat": lat,
                            "lon": lon,
                            "size": max(10, min(50, c["omzet"] / 1000))  # Grootte schalen
                        })
                    else:
                        missing_coords += 1
                
                if missing_coords > 0:
                    st.info(f"ℹ️ {missing_coords} klanten zonder herkenbare postcode (niet op kaart)")
                
                if map_data:
                    df_map = pd.DataFrame(map_data)
                    
                    # Kaart maken met Plotly
                    fig = px.scatter_mapbox(
                        df_map,
                        lat="lat",
                        lon="lon",
                        size="size",
                        color="Omzet",
                        hover_name="Klant",
                        hover_data={
                            "Stad": True,
                            "Postcode": True,
                            "Omzet": ":€,.0f",
                            "Facturen": True,
                            "lat": False,
                            "lon": False,
                            "size": False
                        },
                        color_continuous_scale="Blues",
                        zoom=6,
                        center={"lat": 52.0, "lon": 5.3},
                        height=600
                    )
                    
                    fig.update_layout(
                        mapbox_style="carto-positron",
                        margin={"r": 0, "t": 0, "l": 0, "b": 0}
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # Top klanten tabel
                    st.markdown("---")
                    st.subheader("🏆 Top 15 Klanten op Omzet")
                    
                    df_top_customers = df_map.nlargest(15, "Omzet")[["Klant", "Stad", "Omzet", "Facturen"]]
                    st.dataframe(
                        df_top_customers.style.format({"Omzet": "€{:,.0f}"}),
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Download data
                    st.download_button(
                        "📥 Download klantdata (CSV)",
                        df_map.to_csv(index=False),
                        file_name="lab_projects_klanten.csv",
                        mime="text/csv"
                    )
                else:
                    st.warning("Geen klanten met geldige postcode gevonden")
            else:
                st.info("Geen klantdata beschikbaar")
        else:
            st.info("ℹ️ De klantenkaart is alleen beschikbaar voor LAB Projects. "
                   "Selecteer 'LAB Projects' of 'Alle bedrijven' in de sidebar.")
    
    # =========================================================================
    # TAB 6: KOSTEN
    # =========================================================================
    with tabs[5]:
        st.header("📉 Kostenanalyse")
        if exclude_intercompany:
            st.caption("🔄 Intercompany boekingen uitgesloten")
        
        cost_data = get_cost_data(selected_year, company_id)
        
        # Filter intercompany indien geselecteerd
        if exclude_intercompany and cost_data:
            cost_data = [c for c in cost_data 
                        if not (c.get("partner_id") and c["partner_id"][0] in INTERCOMPANY_PARTNERS)]
        
        if cost_data:
            # Groepeer per account
            account_costs = {}
            
            for c in cost_data:
                account = c.get("account_id")
                if account:
                    name = translate_account_name(account[1])
                    balance = c.get("balance", 0)
                    
                    if name not in account_costs:
                        account_costs[name] = 0
                    account_costs[name] += balance
            
            # Sorteer en toon
            sorted_accounts = sorted(account_costs.items(), key=lambda x: -x[1])
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("🏆 Top 15 Kostenposten")
                top_costs = sorted_accounts[:15]
                df_top = pd.DataFrame(top_costs, columns=["Kostensoort", "Bedrag"])
                
                fig = px.bar(df_top, y="Kostensoort", x="Bedrag", orientation="h",
                            color_discrete_sequence=["#1e3a5f"])
                fig.update_layout(height=500, yaxis={'categoryorder': 'total ascending'})
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("📊 Kostenverdeling")
                df_pie = pd.DataFrame(sorted_accounts[:10], columns=["Kostensoort", "Bedrag"])
                fig2 = px.pie(df_pie, values="Bedrag", names="Kostensoort",
                             color_discrete_sequence=px.colors.sequential.Blues_r)
                st.plotly_chart(fig2, use_container_width=True)
            
            # CSV Export
            st.markdown("---")
            df_all_costs = pd.DataFrame(sorted_accounts, columns=["Kostensoort", "Bedrag"])
            st.download_button(
                "📥 Download alle kosten (CSV)",
                df_all_costs.to_csv(index=False),
                file_name=f"lab_kosten_{selected_year}.csv",
                mime="text/csv"
            )
        else:
            st.info("Geen kostendata beschikbaar")
    
    # =========================================================================
    # TAB 7: CASHFLOW (INTERACTIEF)
    # =========================================================================
    with tabs[6]:
        st.header("📈 Interactieve Cashflow Prognose")

        entity_label = "alle entiteiten" if selected_entity == "Alle bedrijven" else COMPANIES.get(company_id, "")
        st.info(f"💡 Cashflow analyse voor **{entity_label}**: historische data uit bankdagboeken + prognose op basis van openstaande posten.")

        # =====================================================================
        # HUIDIGE POSITIES
        # =====================================================================
        bank_data = get_bank_balances()

        # Haal debiteuren en crediteuren per partner op
        receivables_by_partner = get_receivables_by_partner(company_id)
        payables_by_partner = get_payables_by_partner(company_id)

        # Filter banksaldo op geselecteerde entiteit
        if selected_entity == "Alle bedrijven":
            current_bank = sum(b.get("current_statement_balance", 0) for b in bank_data)
        else:
            current_bank = sum(b.get("current_statement_balance", 0) for b in bank_data
                             if b.get("company_id", [None])[0] == company_id)

        # Totalen voor metrics
        total_receivables = sum(p["total"] for p in receivables_by_partner.values())
        total_payables = sum(p["total"] for p in payables_by_partner.values())

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("🏦 Huidig Banksaldo", f"€{current_bank:,.0f}")
        with col2:
            st.metric("📥 Te Ontvangen (Debiteuren)", f"€{total_receivables:,.0f}")
        with col3:
            st.metric("📤 Te Betalen (Crediteuren)", f"€{total_payables:,.0f}")
        with col4:
            net_position = current_bank + total_receivables - total_payables
            st.metric("💰 Netto Positie", f"€{net_position:,.0f}")

        st.markdown("---")

        # =====================================================================
        # PARTNER FILTERING (UITSLUITINGEN)
        # =====================================================================
        st.subheader("🎯 Partner Selectie voor Prognose")

        with st.expander("📥 Debiteuren uitsluiten van prognose", expanded=False):
            st.caption("Selecteer debiteuren die je wilt uitsluiten van de cashflow prognose (bijv. dubieuze debiteuren)")

            # Sorteer debiteuren op bedrag (hoogste eerst)
            sorted_receivables = sorted(
                [(pid, p) for pid, p in receivables_by_partner.items()],
                key=lambda x: x[1]["total"],
                reverse=True
            )

            excluded_debtors = []
            if sorted_receivables:
                debtor_cols = st.columns(2)
                for idx, (partner_id, partner_data) in enumerate(sorted_receivables[:20]):  # Top 20
                    col = debtor_cols[idx % 2]
                    with col:
                        if st.checkbox(
                            f"{partner_data['name']}: €{partner_data['total']:,.0f}",
                            key=f"exclude_debtor_{partner_id}"
                        ):
                            excluded_debtors.append(partner_id)
            else:
                st.info("Geen openstaande debiteuren gevonden.")

        with st.expander("📤 Crediteuren uitsluiten van prognose", expanded=False):
            st.caption("Selecteer crediteuren die je wilt uitsluiten van de cashflow prognose (bijv. betwiste facturen)")

            # Sorteer crediteuren op bedrag (hoogste eerst)
            sorted_payables = sorted(
                [(pid, p) for pid, p in payables_by_partner.items()],
                key=lambda x: x[1]["total"],
                reverse=True
            )

            excluded_creditors = []
            if sorted_payables:
                creditor_cols = st.columns(2)
                for idx, (partner_id, partner_data) in enumerate(sorted_payables[:20]):  # Top 20
                    col = creditor_cols[idx % 2]
                    with col:
                        if st.checkbox(
                            f"{partner_data['name']}: €{partner_data['total']:,.0f}",
                            key=f"exclude_creditor_{partner_id}"
                        ):
                            excluded_creditors.append(partner_id)
            else:
                st.info("Geen openstaande crediteuren gevonden.")

        # Bereken gefilterde totalen
        filtered_receivables = sum(
            p["total"] for pid, p in receivables_by_partner.items()
            if pid not in excluded_debtors
        )
        filtered_payables = sum(
            p["total"] for pid, p in payables_by_partner.items()
            if pid not in excluded_creditors
        )

        # Toon impact van uitsluiting
        if excluded_debtors or excluded_creditors:
            st.markdown("**Impact van uitsluitingen:**")
            excl_cols = st.columns(2)
            with excl_cols[0]:
                excluded_rec_amount = total_receivables - filtered_receivables
                st.metric(
                    "Uitgesloten Debiteuren",
                    f"€{excluded_rec_amount:,.0f}",
                    delta=f"-€{excluded_rec_amount:,.0f}" if excluded_rec_amount > 0 else None,
                    delta_color="off"
                )
            with excl_cols[1]:
                excluded_pay_amount = total_payables - filtered_payables
                st.metric(
                    "Uitgesloten Crediteuren",
                    f"€{excluded_pay_amount:,.0f}",
                    delta=f"-€{excluded_pay_amount:,.0f}" if excluded_pay_amount > 0 else None,
                    delta_color="off"
                )

        st.markdown("---")

        # =====================================================================
        # HISTORISCHE DATA
        # =====================================================================
        st.subheader("📊 Historische Cashflow (afgelopen weken)")

        weeks_back = st.slider("Aantal weken terug", 4, 16, 8, key="cf_weeks_back")
        historical_data = get_historical_bank_movements(company_id, weeks_back)

        # =====================================================================
        # PROGNOSE PARAMETERS
        # =====================================================================
        st.subheader("⚙️ Prognose Parameters")

        # Rolling forecast optie
        use_rolling_forecast = st.checkbox(
            "🔄 Rolling Forecast (gebruik historische gemiddelden)",
            value=False,
            key="cf_rolling_forecast",
            help="Indien aangevinkt, worden de wekelijkse omzet en kosten automatisch berekend op basis van historische bankdata"
        )

        # Bereken historische gemiddelden voor rolling forecast
        if historical_data and use_rolling_forecast:
            hist_inflows = [w["inflow"] for w in historical_data.values()]
            hist_outflows = [w["outflow"] for w in historical_data.values()]
            avg_weekly_inflow = sum(hist_inflows) / len(hist_inflows) if hist_inflows else 50000
            avg_weekly_outflow = sum(hist_outflows) / len(hist_outflows) if hist_outflows else 45000
            st.info(f"📊 Historisch gemiddelde (laatste {len(historical_data)} weken): Ontvangsten €{avg_weekly_inflow:,.0f}/week | Uitgaven €{avg_weekly_outflow:,.0f}/week")
        else:
            avg_weekly_inflow = 50000
            avg_weekly_outflow = 45000

        param_cols = st.columns(4)
        with param_cols[0]:
            if use_rolling_forecast:
                weekly_revenue = avg_weekly_inflow
                st.metric("Wekelijkse omzet (auto)", f"€{weekly_revenue:,.0f}")
            else:
                weekly_revenue = st.number_input(
                    "Verwachte wekelijkse omzet",
                    value=50000,
                    step=5000,
                    key="cf_weekly_rev"
                )
        with param_cols[1]:
            if use_rolling_forecast:
                weekly_costs = avg_weekly_outflow
                st.metric("Wekelijkse kosten (auto)", f"€{weekly_costs:,.0f}")
            else:
                weekly_costs = st.number_input(
                    "Verwachte wekelijkse kosten",
                    value=45000,
                    step=5000,
                    key="cf_weekly_cost"
                )
        with param_cols[2]:
            collection_rate = st.slider(
                "Incasso % debiteuren/week",
                0, 100, 25,
                key="cf_collection_rate"
            )
        with param_cols[3]:
            payment_rate = st.slider(
                "Betaling % crediteuren/week",
                0, 100, 20,
                key="cf_payment_rate"
            )

        forecast_weeks = st.slider("Aantal weken vooruit", 4, 24, 12, key="cf_forecast_weeks")

        # Import en bereken huidige week (nodig voor BTW berekening)
        from datetime import timedelta
        today = datetime.now().date()
        current_week_start = today - timedelta(days=today.weekday())

        # =====================================================================
        # VASTE LASTEN (LONEN & BTW)
        # =====================================================================
        st.markdown("---")
        st.subheader("💼 Vaste Lasten")
        st.caption("Voeg terugkerende kosten toe die niet in de crediteuren staan")

        # Haal BTW-data op uit de 15* rekeningen
        vat_monthly_data = get_vat_monthly_data(company_id if selected_entity != "Alle bedrijven" else None, months_back=6)

        # Bereken gemiddelde maandelijkse BTW (voor kwartaalprognose)
        if vat_monthly_data:
            avg_monthly_vat = sum(m["net_vat"] for m in vat_monthly_data) / len(vat_monthly_data)
            avg_quarterly_vat = avg_monthly_vat * 3  # Kwartaal = 3 maanden
            suggested_vat = int(max(0, avg_quarterly_vat))  # Alleen positief (af te dragen)
        else:
            avg_monthly_vat = 0
            avg_quarterly_vat = 0
            suggested_vat = 0

        fixed_costs_cols = st.columns(3)
        with fixed_costs_cols[0]:
            monthly_salaries = st.number_input(
                "Maandelijkse loonkosten (€)",
                value=0,
                step=1000,
                min_value=0,
                key="cf_monthly_salaries",
                help="Totale maandelijkse loonkosten inclusief werkgeverslasten (betaling in 3de week van de maand)"
            )
        with fixed_costs_cols[1]:
            vat_payment = st.number_input(
                "BTW afdracht per kwartaal (€)",
                value=suggested_vat,
                step=1000,
                min_value=0,
                key="cf_vat_payment",
                help="Berekend op basis van 15* rekeningen (BTW). Pas aan indien nodig."
            )
        with fixed_costs_cols[2]:
            other_fixed_costs = st.number_input(
                "Overige vaste maandkosten (€)",
                value=0,
                step=500,
                min_value=0,
                key="cf_other_fixed",
                help="Huur, verzekeringen, abonnementen, etc."
            )

        # Toon BTW details uit 15* rekeningen
        if vat_monthly_data:
            with st.expander("📊 BTW Historie (15* rekeningen)", expanded=False):
                st.caption("Maandelijkse BTW op basis van de 15* rekeningen in Odoo")
                vat_df = pd.DataFrame(vat_monthly_data)
                vat_df.columns = ["Maand", "Voorbelasting (debet)", "Af te dragen (credit)", "Netto BTW"]
                vat_df["Voorbelasting (debet)"] = vat_df["Voorbelasting (debet)"].apply(lambda x: f"€{x:,.0f}")
                vat_df["Af te dragen (credit)"] = vat_df["Af te dragen (credit)"].apply(lambda x: f"€{x:,.0f}")
                vat_df["Netto BTW"] = vat_df["Netto BTW"].apply(lambda x: f"€{x:,.0f}")
                st.dataframe(vat_df, use_container_width=True, hide_index=True)
                st.info(f"💡 Gemiddelde maandelijkse netto BTW: **€{avg_monthly_vat:,.0f}** → Kwartaalprognose: **€{avg_quarterly_vat:,.0f}**")

        # Bereken wanneer BTW betaald moet worden (maanden na kwartaaleinde: jan, apr, jul, okt)
        def get_vat_payment_weeks(start_date, num_weeks):
            """Bepaal in welke weken BTW betaald moet worden"""
            vat_weeks = []
            vat_months = [1, 4, 7, 10]  # Januari, April, Juli, Oktober

            for week in range(1, num_weeks + 1):
                week_date = start_date + timedelta(weeks=week)
                # BTW wordt betaald in de eerste week van de BTW-maand
                if week_date.month in vat_months and week_date.day <= 7:
                    # Check of dit de eerste week van de maand is
                    first_of_month = week_date.replace(day=1)
                    if (week_date - first_of_month).days < 7:
                        vat_weeks.append(week)
            return vat_weeks

        # Bereken wanneer lonen betaald worden (3de week van elke maand)
        def get_salary_payment_weeks(start_date, num_weeks):
            """Bepaal in welke weken lonen betaald worden (3de week van de maand)"""
            salary_weeks = []

            for week in range(1, num_weeks + 1):
                week_date = start_date + timedelta(weeks=week)
                # 3de week van de maand = dag 15-21
                if 15 <= week_date.day <= 21:
                    salary_weeks.append(week)
            return salary_weeks

        vat_payment_weeks = get_vat_payment_weeks(current_week_start, forecast_weeks) if vat_payment > 0 else []
        salary_payment_weeks = get_salary_payment_weeks(current_week_start, forecast_weeks) if monthly_salaries > 0 else []

        if monthly_salaries > 0 or vat_payment > 0 or other_fixed_costs > 0:
            info_parts = []
            if monthly_salaries > 0:
                info_parts.append(f"Lonen €{monthly_salaries:,.0f}/maand (betaling 3de week)")
            if other_fixed_costs > 0:
                info_parts.append(f"Overige vaste kosten €{other_fixed_costs/4.33:,.0f}/week")
            if vat_payment > 0 and vat_payment_weeks:
                info_parts.append(f"BTW afdracht €{vat_payment:,.0f} in weken: {vat_payment_weeks}")
            st.info(f"💡 Vaste lasten: {' | '.join(info_parts)}")

        # =====================================================================
        # GECOMBINEERDE DATASET BOUWEN
        # =====================================================================
        all_data = []

        # 1. Historische weken toevoegen (WERKELIJKE DATA)
        if historical_data:
            sorted_weeks = sorted(historical_data.keys())

            # Bereken startsaldo door terug te rekenen
            running_balance = current_bank
            weekly_changes = []
            for week_key in reversed(sorted_weeks):
                week_data = historical_data[week_key]
                weekly_changes.append((week_key, week_data["net"]))

            # Bereken saldo aan het begin van de historische periode
            historical_start_balance = current_bank
            for week_key, net_change in weekly_changes:
                historical_start_balance -= net_change

            # Voeg historische weken toe met berekend saldo
            running_balance = historical_start_balance
            for week_key in sorted_weeks:
                week_data = historical_data[week_key]
                week_start = week_data["week_start"]
                week_num = (current_week_start - week_start).days // 7

                running_balance += week_data["net"]

                all_data.append({
                    "week_key": week_key,
                    "week_label": f"Week -{week_num}" if week_num > 0 else "Huidige week",
                    "week_start": week_start,
                    "is_forecast": False,
                    "inflow": week_data["inflow"],
                    "outflow": week_data["outflow"],
                    "net": week_data["net"],
                    "balance": running_balance
                })

        # 2. Huidige week (Week 0) - transitiepunt
        all_data.append({
            "week_key": current_week_start.strftime("%Y-%m-%d"),
            "week_label": "Nu",
            "week_start": current_week_start,
            "is_forecast": False,
            "inflow": 0,
            "outflow": 0,
            "net": 0,
            "balance": current_bank
        })

        # 3. Prognose weken toevoegen
        balance = current_bank
        remaining_rec = filtered_receivables
        remaining_pay = filtered_payables

        # Bereken wekelijkse vaste lasten
        weekly_other_fixed = other_fixed_costs / 4.33

        for week in range(1, forecast_weeks + 1):
            week_start = current_week_start + timedelta(weeks=week)

            # Ontvangsten uit debiteuren
            collections = remaining_rec * (collection_rate / 100)
            remaining_rec -= collections
            inflow = weekly_revenue + collections

            # Betalingen aan crediteuren
            payments = remaining_pay * (payment_rate / 100)
            remaining_pay -= payments

            # Lonen alleen in de 3de week van de maand (volledige maandbedrag)
            salaries_this_week = monthly_salaries if week in salary_payment_weeks else 0

            # Vaste lasten toevoegen
            fixed_costs_this_week = salaries_this_week + weekly_other_fixed

            # BTW afdracht in specifieke weken
            vat_this_week = vat_payment if week in vat_payment_weeks else 0

            outflow = weekly_costs + payments + fixed_costs_this_week + vat_this_week

            # Nieuw saldo
            balance = balance + inflow - outflow

            # Bepaal label met extra info bij loon/BTW week
            week_label = f"Week +{week}"
            label_extras = []
            if salaries_this_week > 0:
                label_extras.append("Lonen")
            if vat_this_week > 0:
                label_extras.append("BTW")
            if label_extras:
                week_label += f" ({', '.join(label_extras)})"

            all_data.append({
                "week_key": week_start.strftime("%Y-%m-%d"),
                "week_label": week_label,
                "week_start": week_start,
                "is_forecast": True,
                "inflow": inflow,
                "outflow": outflow,
                "net": inflow - outflow,
                "balance": balance,
                "salaries": salaries_this_week,
                "vat": vat_this_week,
                "other_fixed": weekly_other_fixed
            })

        df_combined = pd.DataFrame(all_data)

        # =====================================================================
        # INTERACTIEVE GRAFIEK
        # =====================================================================
        st.subheader("📈 Cashflow Overzicht")

        fig = go.Figure()

        # Historische data (solide lijn)
        df_historical = df_combined[~df_combined["is_forecast"]]
        if not df_historical.empty:
            fig.add_trace(go.Scatter(
                x=df_historical["week_label"],
                y=df_historical["balance"],
                mode="lines+markers",
                name="Werkelijk Saldo",
                line=dict(color="#2E7D32", width=3),
                marker=dict(size=8, symbol="circle"),
                hovertemplate="<b>%{x}</b><br>Saldo: €%{y:,.0f}<extra></extra>"
            ))

        # Prognose data (stippellijn)
        df_forecast = df_combined[df_combined["is_forecast"]]
        if not df_forecast.empty:
            # Voeg "Nu" punt toe aan prognose voor continue lijn
            now_row = df_combined[df_combined["week_label"] == "Nu"]
            df_forecast_with_now = pd.concat([now_row, df_forecast])

            fig.add_trace(go.Scatter(
                x=df_forecast_with_now["week_label"],
                y=df_forecast_with_now["balance"],
                mode="lines+markers",
                name="Prognose Saldo",
                line=dict(color="#1565C0", width=3, dash="dash"),
                marker=dict(size=8, symbol="diamond"),
                hovertemplate="<b>%{x}</b><br>Prognose: €%{y:,.0f}<extra></extra>"
            ))

        # Inflow/Outflow bars
        fig.add_trace(go.Bar(
            x=df_combined["week_label"],
            y=df_combined["inflow"],
            name="Ontvangsten",
            marker_color="rgba(76, 175, 80, 0.5)",
            hovertemplate="<b>%{x}</b><br>Ontvangsten: €%{y:,.0f}<extra></extra>"
        ))

        fig.add_trace(go.Bar(
            x=df_combined["week_label"],
            y=[-x for x in df_combined["outflow"]],
            name="Uitgaven",
            marker_color="rgba(244, 67, 54, 0.5)",
            hovertemplate="<b>%{x}</b><br>Uitgaven: €%{y:,.0f}<extra></extra>"
        ))

        # Nul-lijn
        fig.add_hline(y=0, line_dash="dash", line_color="red", line_width=1)

        # Verticale lijn bij "Nu"
        now_index = list(df_combined["week_label"]).index("Nu")
        fig.add_vline(
            x=now_index,
            line_dash="dot",
            line_color="gray",
            annotation_text="Vandaag",
            annotation_position="top"
        )

        fig.update_layout(
            height=500,
            title="📈 Cashflow: Historisch & Prognose",
            xaxis_title="Week",
            yaxis_title="Bedrag (€)",
            barmode="relative",
            hovermode="x unified",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )

        st.plotly_chart(fig, use_container_width=True)

        # =====================================================================
        # DETAIL TABELLEN
        # =====================================================================
        tab_hist, tab_forecast, tab_partners = st.tabs([
            "📜 Historische Data",
            "🔮 Prognose Details",
            "👥 Openstaande Posten per Partner"
        ])

        with tab_hist:
            st.caption("Werkelijke bankmutaties per week (uit bankdagboeken)")
            df_hist_display = df_combined[~df_combined["is_forecast"]].copy()
            if not df_hist_display.empty:
                df_hist_display["week_start"] = pd.to_datetime(df_hist_display["week_start"]).dt.strftime("%d-%m-%Y")
                st.dataframe(
                    df_hist_display[["week_label", "week_start", "inflow", "outflow", "net", "balance"]].rename(
                        columns={
                            "week_label": "Week",
                            "week_start": "Week Start",
                            "inflow": "Ontvangsten",
                            "outflow": "Uitgaven",
                            "net": "Netto",
                            "balance": "Saldo"
                        }
                    ).style.format({
                        "Ontvangsten": "€{:,.0f}",
                        "Uitgaven": "€{:,.0f}",
                        "Netto": "€{:,.0f}",
                        "Saldo": "€{:,.0f}"
                    }),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Geen historische data beschikbaar voor de geselecteerde periode.")

        with tab_forecast:
            st.caption("Geprojecteerde cashflow op basis van openstaande posten, vaste lasten en parameters")
            df_fc_display = df_combined[df_combined["is_forecast"]].copy()
            if not df_fc_display.empty:
                df_fc_display["week_start"] = pd.to_datetime(df_fc_display["week_start"]).dt.strftime("%d-%m-%Y")

                # Toon uitgebreide tabel met vaste lasten indien van toepassing
                if monthly_salaries > 0 or vat_payment > 0 or other_fixed_costs > 0:
                    # Voeg vaste lasten kolommen toe als ze bestaan
                    display_cols = ["week_label", "week_start", "inflow", "outflow", "salaries", "vat", "other_fixed", "net", "balance"]
                    rename_cols = {
                        "week_label": "Week",
                        "week_start": "Week Start",
                        "inflow": "Ontvangsten",
                        "outflow": "Totaal Uitgaven",
                        "salaries": "Lonen",
                        "vat": "BTW",
                        "other_fixed": "Overig Vast",
                        "net": "Netto",
                        "balance": "Saldo"
                    }
                    format_dict = {
                        "Ontvangsten": "€{:,.0f}",
                        "Totaal Uitgaven": "€{:,.0f}",
                        "Lonen": "€{:,.0f}",
                        "BTW": "€{:,.0f}",
                        "Overig Vast": "€{:,.0f}",
                        "Netto": "€{:,.0f}",
                        "Saldo": "€{:,.0f}"
                    }
                else:
                    display_cols = ["week_label", "week_start", "inflow", "outflow", "net", "balance"]
                    rename_cols = {
                        "week_label": "Week",
                        "week_start": "Week Start",
                        "inflow": "Ontvangsten",
                        "outflow": "Uitgaven",
                        "net": "Netto",
                        "balance": "Saldo"
                    }
                    format_dict = {
                        "Ontvangsten": "€{:,.0f}",
                        "Uitgaven": "€{:,.0f}",
                        "Netto": "€{:,.0f}",
                        "Saldo": "€{:,.0f}"
                    }

                # Filter alleen bestaande kolommen
                existing_cols = [c for c in display_cols if c in df_fc_display.columns]
                st.dataframe(
                    df_fc_display[existing_cols].rename(columns=rename_cols).style.format(format_dict),
                    use_container_width=True,
                    hide_index=True
                )

        with tab_partners:
            partner_col1, partner_col2 = st.columns(2)

            with partner_col1:
                st.markdown("**📥 Top Debiteuren (Te Ontvangen)**")
                if receivables_by_partner:
                    debtor_list = [
                        {
                            "Partner": p["name"],
                            "Bedrag": p["total"],
                            "Status": "❌ Uitgesloten" if pid in excluded_debtors else "✅ In prognose"
                        }
                        for pid, p in sorted(
                            receivables_by_partner.items(),
                            key=lambda x: x[1]["total"],
                            reverse=True
                        )[:15]
                    ]
                    st.dataframe(
                        pd.DataFrame(debtor_list).style.format({"Bedrag": "€{:,.0f}"}),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("Geen openstaande debiteuren.")

            with partner_col2:
                st.markdown("**📤 Top Crediteuren (Te Betalen)**")
                if payables_by_partner:
                    creditor_list = [
                        {
                            "Partner": p["name"],
                            "Bedrag": p["total"],
                            "Status": "❌ Uitgesloten" if pid in excluded_creditors else "✅ In prognose"
                        }
                        for pid, p in sorted(
                            payables_by_partner.items(),
                            key=lambda x: x[1]["total"],
                            reverse=True
                        )[:15]
                    ]
                    st.dataframe(
                        pd.DataFrame(creditor_list).style.format({"Bedrag": "€{:,.0f}"}),
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info("Geen openstaande crediteuren.")

        # =====================================================================
        # EXPORT FUNCTIE
        # =====================================================================
        st.markdown("---")
        st.download_button(
            "📥 Download Cashflow Data (CSV)",
            df_combined.to_csv(index=False),
            file_name=f"cashflow_prognose_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    
    # =========================================================================
    # TAB 8: BALANS (KWADRANT)
    # =========================================================================
    with tabs[7]:
        st.header("📊 Balans (Kwadrant)")
        
        # Peildatum selectie
        balance_date = st.date_input(
            "Peildatum",
            value=datetime.now().date(),
            max_value=datetime.now().date(),
            key="balance_date"
        )
        
        @st.cache_data(ttl=3600)
        def get_balance_sheet_data(date_str, comp_id=None):
            """Haal balanssaldi op per account type"""
            domain = [
                ("date", "<=", date_str),
                ("parent_state", "=", "posted")
            ]
            if comp_id:
                domain.append(("company_id", "=", comp_id))
            
            # Groepeer per account
            result = odoo_read_group(
                "account.move.line",
                domain,
                ["balance:sum"],
                ["account_id"]
            )
            
            # Haal account details op
            account_ids = [r["account_id"][0] for r in result if r.get("account_id")]
            if not account_ids:
                return {}
            
            accounts = odoo_call(
                "account.account",
                "search_read",
                [("id", "in", account_ids)],
                fields=["id", "code", "name", "account_type"]
            )
            account_map = {a["id"]: a for a in accounts}
            
            # Combineer data
            balance_data = {}
            for r in result:
                if not r.get("account_id"):
                    continue
                acc_id = r["account_id"][0]
                acc = account_map.get(acc_id, {})
                acc_type = acc.get("account_type", "other")
                code = acc.get("code", "")
                name = acc.get("name", "")
                balance = r.get("balance", 0)
                
                if acc_type not in balance_data:
                    balance_data[acc_type] = []
                balance_data[acc_type].append({
                    "code": code,
                    "name": name,
                    "balance": balance
                })
            
            return balance_data
        
        balance_data = get_balance_sheet_data(str(balance_date), company_id)
        
        # Categorieën mapping (Nederlands)
        ACTIVA_TYPES = {
            "asset_fixed": "Vaste activa",
            "asset_non_current": "Vaste activa (overig)",
            "asset_current": "Vlottende activa",
            "asset_prepayments": "Vooruitbetalingen",
            "asset_receivable": "Vorderingen",
            "asset_cash": "Liquide middelen"
        }
        
        PASSIVA_TYPES = {
            "equity": "Eigen vermogen",
            "equity_unaffected": "Onverdeeld resultaat",
            "liability_non_current": "Langlopende schulden",
            "liability_current": "Kortlopende schulden",
            "liability_payable": "Crediteuren",
            "liability_credit_card": "Creditcard schulden"
        }
        
        def format_balance_section(types_dict, data, invert_sign=False):
            """Format een sectie van de balans"""
            rows = []
            total = 0
            for acc_type, label in types_dict.items():
                if acc_type in data:
                    items = data[acc_type]
                    subtotal = sum(item["balance"] for item in items)
                    if invert_sign:
                        subtotal = -subtotal
                    if subtotal != 0:
                        rows.append({"Categorie": f"**{label}**", "Bedrag": subtotal, "is_header": True})
                        # Sorteer items op code
                        sorted_items = sorted(items, key=lambda x: x["code"])
                        for item in sorted_items:
                            bal = -item["balance"] if invert_sign else item["balance"]
                            if bal != 0:
                                rows.append({
                                    "Categorie": f"  {item['code']} - {item['name'][:40]}",
                                    "Bedrag": bal,
                                    "is_header": False
                                })
                        total += subtotal
            return rows, total
        
        # Layout: Activa links, Passiva rechts
        col_activa, col_passiva = st.columns(2)
        
        with col_activa:
            st.subheader("ACTIVA")
            activa_rows, activa_total = format_balance_section(ACTIVA_TYPES, balance_data, invert_sign=False)
            
            if activa_rows:
                for row in activa_rows:
                    if row["is_header"]:
                        st.markdown(f"{row['Categorie']}: **€{row['Bedrag']:,.0f}**")
                    # Details kunnen worden uitgevouwen met expander indien gewenst
                
                st.markdown("---")
                st.markdown(f"### Totaal Activa: €{activa_total:,.0f}")
            else:
                st.info("Geen activa data beschikbaar")
        
        with col_passiva:
            st.subheader("PASSIVA")
            passiva_rows, passiva_total = format_balance_section(PASSIVA_TYPES, balance_data, invert_sign=True)
            
            if passiva_rows:
                for row in passiva_rows:
                    if row["is_header"]:
                        st.markdown(f"{row['Categorie']}: **€{row['Bedrag']:,.0f}**")
                
                st.markdown("---")
                st.markdown(f"### Totaal Passiva: €{passiva_total:,.0f}")
            else:
                st.info("Geen passiva data beschikbaar")
        
        # Balanscontrole
        st.markdown("---")
        verschil = activa_total - passiva_total
        if abs(verschil) < 1:
            st.success(f"✅ Balans in evenwicht (verschil: €{verschil:,.2f})")
        else:
            st.warning(f"⚠️ Balansverschil: €{verschil:,.0f}")
        
        # Detail tabel met alle rekeningen
        with st.expander("📋 Gedetailleerd overzicht per rekening"):
            all_accounts = []
            for acc_type, items in balance_data.items():
                type_label = ACTIVA_TYPES.get(acc_type) or PASSIVA_TYPES.get(acc_type, acc_type)
                for item in items:
                    if item["balance"] != 0:
                        all_accounts.append({
                            "Code": item["code"],
                            "Naam": item["name"],
                            "Type": type_label,
                            "Saldo": item["balance"]
                        })
            
            if all_accounts:
                df_accounts = pd.DataFrame(all_accounts)
                df_accounts = df_accounts.sort_values("Code")
                st.dataframe(
                    df_accounts.style.format({"Saldo": "€{:,.0f}"}),
                    use_container_width=True,
                    hide_index=True
                )
                
                # Download optie
                csv = df_accounts.to_csv(index=False)
                st.download_button(
                    "📥 Download Balans CSV",
                    csv,
                    f"balans_{balance_date}.csv",
                    "text/csv"
                )

    # =========================================================================
    # TAB 9: AI CHAT
    # =========================================================================
    with tabs[8]:
        st.header("💬 AI Financial Assistant")
        
        # Check voor OpenAI API key
        if not get_openai_key():
            st.warning("👈 Voer je OpenAI API Key in via de sidebar om de chatbot te gebruiken")
            st.info("""
            **Wat kan de AI Assistant?**
            - Vragen beantwoorden over omzet, kosten en winst
            - Facturen en betalingen opzoeken
            - Klant- en leveranciersgegevens analyseren
            - Specifieke Odoo queries uitvoeren
            
            **Voorbeeldvragen:**
            - "Wat is de omzet van LAB Shops in januari 2025?"
            - "Toon de top 5 klanten op basis van omzet"
            - "Hoeveel openstaande facturen zijn er?"
            - "Wat zijn de grootste kostenposten dit kwartaal?"
            """)
        else:
            # Initialiseer chat geschiedenis
            if "chat_messages" not in st.session_state:
                st.session_state.chat_messages = []
            
            # Context info voor de chatbot
            context_info = f"""
            - Geselecteerd jaar: {selected_year}
            - Geselecteerde entiteit: {selected_entity}
            - Company ID: {company_id if company_id else 'Alle bedrijven'}
            - Intercompany uitgesloten: {exclude_intercompany}
            - Huidige datum: {datetime.now().strftime('%Y-%m-%d')}
            """
            
            # Chat container
            chat_container = st.container()
            
            # Toon chat geschiedenis
            with chat_container:
                for message in st.session_state.chat_messages:
                    with st.chat_message(message["role"]):
                        st.markdown(message["content"])
                        if message.get("data"):
                            with st.expander("📊 Onderliggende data"):
                                st.json(message["data"][:20] if len(message.get("data", [])) > 20 else message.get("data"))
            
            # Chat input
            if prompt := st.chat_input("Stel een vraag over je financiële data..."):
                # Toon user message
                with st.chat_message("user"):
                    st.markdown(prompt)
                st.session_state.chat_messages.append({"role": "user", "content": prompt})
                
                # Genereer antwoord
                with st.chat_message("assistant"):
                    with st.spinner("Denken..."):
                        response, query_data = process_chat_message(
                            prompt, 
                            st.session_state.chat_messages, 
                            context_info
                        )
                        st.markdown(response)
                        
                        if query_data:
                            with st.expander("📊 Onderliggende data"):
                                st.json(query_data[:20] if len(query_data) > 20 else query_data)
                
                # Sla antwoord op
                st.session_state.chat_messages.append({
                    "role": "assistant", 
                    "content": response,
                    "data": query_data
                })
            
            # Clear chat knop
            col1, col2, col3 = st.columns([1, 1, 3])
            with col1:
                if st.button("🗑️ Wis chat"):
                    st.session_state.chat_messages = []
                    st.rerun()
            with col2:
                if st.button("💡 Voorbeelden"):
                    st.session_state.show_examples = not st.session_state.get("show_examples", False)
                    st.rerun()
            
            # Toon voorbeeldvragen
            if st.session_state.get("show_examples", False):
                st.markdown("---")
                st.markdown("**Voorbeeldvragen die je kunt stellen:**")
                examples = [
                    "Wat is de totale omzet van dit jaar?",
                    "Toon de top 10 klanten op omzet",
                    "Hoeveel openstaande inkoopfacturen zijn er?",
                    "Wat zijn de grootste kostenposten?",
                    "Vergelijk de omzet van Q1 met Q2",
                    "Welke leveranciers hebben de hoogste facturen?",
                    "Wat is het banksaldo op dit moment?",
                    "Toon alle facturen boven €10.000"
                ]
                for ex in examples:
                    if st.button(f"💬 {ex}", key=f"ex_{ex[:20]}"):
                        st.session_state.chat_messages.append({"role": "user", "content": ex})
                        st.rerun()

    # =========================================================================
    # TAB 10: MAANDAFSLUITING (FINANCIAL CLOSE)
    # =========================================================================
    with tabs[9]:
        st.header("📋 Maandafsluiting (Financial Close)")

        # Initialize session state for Financial Close authentication
        if "financial_close_authenticated" not in st.session_state:
            st.session_state.financial_close_authenticated = False
        if "financial_close_password_attempt" not in st.session_state:
            st.session_state.financial_close_password_attempt = ""

        # Check if password is configured
        password_configured = is_financial_close_configured()

        def show_financial_close_content():
            """Display the Financial Close content after authentication."""

            st.markdown("---")

            # =================================================================
            # PERIOD SELECTION
            # =================================================================
            st.subheader("📅 Periode Selectie")

            col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
            with col1:
                close_year = st.selectbox(
                    "Jaar",
                    options=list(range(datetime.now().year, 2021, -1)),
                    key="fc_year"
                )
            with col2:
                close_month = st.selectbox(
                    "Maand",
                    options=list(range(1, 13)),
                    format_func=lambda x: [
                        "Januari", "Februari", "Maart", "April", "Mei", "Juni",
                        "Juli", "Augustus", "September", "Oktober", "November", "December"
                    ][x - 1],
                    index=datetime.now().month - 2 if datetime.now().month > 1 else 11,
                    key="fc_month"
                )
            with col3:
                close_company = st.selectbox(
                    "Entiteit",
                    options=["Alle bedrijven"] + list(COMPANIES.values()),
                    key="fc_company"
                )
            with col4:
                btw_monthly = st.checkbox(
                    "BTW per maand",
                    value=False,
                    key="fc_btw_monthly",
                    help="Vink aan als de BTW maandelijks wordt aangegeven i.p.v. per kwartaal"
                )

            fc_company_id = None
            if close_company != "Alle bedrijven":
                fc_company_id = [k for k, v in COMPANIES.items() if v == close_company][0]

            # Calculate period dates
            from calendar import monthrange
            period_start = f"{close_year}-{close_month:02d}-01"
            period_end_day = monthrange(close_year, close_month)[1]
            period_end = f"{close_year}-{close_month:02d}-{period_end_day:02d}"

            # Previous period for comparison
            if close_month == 1:
                prev_year, prev_month = close_year - 1, 12
            else:
                prev_year, prev_month = close_year, close_month - 1
            prev_start = f"{prev_year}-{prev_month:02d}-01"
            prev_end_day = monthrange(prev_year, prev_month)[1]
            prev_end = f"{prev_year}-{prev_month:02d}-{prev_end_day:02d}"

            month_names = [
                "Januari", "Februari", "Maart", "April", "Mei", "Juni",
                "Juli", "Augustus", "September", "Oktober", "November", "December"
            ]
            period_label = f"{month_names[close_month - 1]} {close_year}"
            prev_period_label = f"{month_names[prev_month - 1]} {prev_year}"

            # BTW period calculation (monthly or quarterly)
            if btw_monthly:
                # Monthly BTW - same as regular period
                btw_period_start = period_start
                btw_period_end = period_end
                btw_prev_start = prev_start
                btw_prev_end = prev_end
                btw_period_label = period_label
                btw_prev_label = prev_period_label
            else:
                # Quarterly BTW - calculate quarter based on selected month
                quarter = (close_month - 1) // 3 + 1
                quarter_start_month = (quarter - 1) * 3 + 1
                quarter_end_month = quarter * 3
                btw_period_start = f"{close_year}-{quarter_start_month:02d}-01"
                btw_period_end_day = monthrange(close_year, quarter_end_month)[1]
                btw_period_end = f"{close_year}-{quarter_end_month:02d}-{btw_period_end_day:02d}"
                btw_period_label = f"Q{quarter} {close_year}"

                # Previous quarter
                if quarter == 1:
                    prev_quarter = 4
                    prev_quarter_year = close_year - 1
                else:
                    prev_quarter = quarter - 1
                    prev_quarter_year = close_year
                prev_quarter_start_month = (prev_quarter - 1) * 3 + 1
                prev_quarter_end_month = prev_quarter * 3
                btw_prev_start = f"{prev_quarter_year}-{prev_quarter_start_month:02d}-01"
                btw_prev_end_day = monthrange(prev_quarter_year, prev_quarter_end_month)[1]
                btw_prev_end = f"{prev_quarter_year}-{prev_quarter_end_month:02d}-{btw_prev_end_day:02d}"
                btw_prev_label = f"Q{prev_quarter} {prev_quarter_year}"

            st.info(f"📊 Periode: **{period_label}** | Vergelijking met: **{prev_period_label}** | BTW periode: **{btw_period_label}** ({'maandelijks' if btw_monthly else 'per kwartaal'})")

            # =================================================================
            # DATA FETCHING FUNCTIONS FOR FINANCIAL CLOSE
            # =================================================================

            @st.cache_data(ttl=1800)
            def get_period_revenue(start_date, end_date, comp_id=None):
                """Get revenue for a specific period."""
                domain = [
                    ("account_id.code", ">=", "800000"),
                    ("account_id.code", "<", "900000"),
                    ("date", ">=", start_date),
                    ("date", "<=", end_date),
                    ("parent_state", "=", "posted")
                ]
                if comp_id:
                    domain.append(("company_id", "=", comp_id))
                result = odoo_read_group("account.move.line", domain, ["balance:sum"], [])
                return -sum(r.get("balance", 0) for r in result)

            @st.cache_data(ttl=1800)
            def get_period_costs(start_date, end_date, comp_id=None):
                """Get costs for a specific period (4*, 6*, 7* accounts)."""
                total = 0
                for prefix, next_prefix in [("400000", "500000"), ("600000", "700000"), ("700000", "800000")]:
                    domain = [
                        ("account_id.code", ">=", prefix),
                        ("account_id.code", "<", next_prefix),
                        ("date", ">=", start_date),
                        ("date", "<=", end_date),
                        ("parent_state", "=", "posted")
                    ]
                    if comp_id:
                        domain.append(("company_id", "=", comp_id))
                    result = odoo_read_group("account.move.line", domain, ["balance:sum"], [])
                    total += sum(r.get("balance", 0) for r in result)
                return total

            @st.cache_data(ttl=1800)
            def get_period_revenue_by_account(start_date, end_date, comp_id=None):
                """Get revenue grouped by account for the period."""
                domain = [
                    ("account_id.code", ">=", "800000"),
                    ("account_id.code", "<", "900000"),
                    ("date", ">=", start_date),
                    ("date", "<=", end_date),
                    ("parent_state", "=", "posted")
                ]
                if comp_id:
                    domain.append(("company_id", "=", comp_id))
                return odoo_read_group("account.move.line", domain, ["balance:sum"], ["account_id"])

            @st.cache_data(ttl=1800)
            def get_period_costs_by_account(start_date, end_date, comp_id=None):
                """Get costs grouped by account for the period."""
                all_results = []
                for prefix, next_prefix in [("400000", "500000"), ("600000", "700000"), ("700000", "800000")]:
                    domain = [
                        ("account_id.code", ">=", prefix),
                        ("account_id.code", "<", next_prefix),
                        ("date", ">=", start_date),
                        ("date", "<=", end_date),
                        ("parent_state", "=", "posted")
                    ]
                    if comp_id:
                        domain.append(("company_id", "=", comp_id))
                    result = odoo_read_group("account.move.line", domain, ["balance:sum"], ["account_id"])
                    all_results.extend(result)
                return all_results

            @st.cache_data(ttl=1800)
            def get_unposted_entries(start_date, end_date, comp_id=None):
                """Get draft/unposted journal entries for the period."""
                domain = [
                    ("date", ">=", start_date),
                    ("date", "<=", end_date),
                    ("state", "=", "draft")
                ]
                if comp_id:
                    domain.append(("company_id", "=", comp_id))
                return odoo_call(
                    "account.move", "search_read",
                    domain,
                    ["name", "date", "amount_total", "partner_id", "company_id", "move_type"],
                    limit=500
                )

            @st.cache_data(ttl=1800)
            def get_unreconciled_items(comp_id=None):
                """Get unreconciled receivables and payables."""
                # Receivables
                rec_domain = [
                    ("account_id.account_type", "=", "asset_receivable"),
                    ("parent_state", "=", "posted"),
                    ("amount_residual", "!=", 0),
                    ("reconciled", "=", False)
                ]
                if comp_id:
                    rec_domain.append(("company_id", "=", comp_id))
                receivables = odoo_call(
                    "account.move.line", "search_read",
                    rec_domain,
                    ["date", "name", "partner_id", "amount_residual", "company_id"],
                    limit=1000
                )

                # Payables
                pay_domain = [
                    ("account_id.account_type", "=", "liability_payable"),
                    ("parent_state", "=", "posted"),
                    ("amount_residual", "!=", 0),
                    ("reconciled", "=", False)
                ]
                if comp_id:
                    pay_domain.append(("company_id", "=", comp_id))
                payables = odoo_call(
                    "account.move.line", "search_read",
                    pay_domain,
                    ["date", "name", "partner_id", "amount_residual", "company_id"],
                    limit=1000
                )

                return receivables, payables

            @st.cache_data(ttl=1800)
            def get_balance_check(date_str, comp_id=None):
                """Get total debit and credit for balance verification."""
                domain = [
                    ("date", "<=", date_str),
                    ("parent_state", "=", "posted")
                ]
                if comp_id:
                    domain.append(("company_id", "=", comp_id))

                result = odoo_read_group(
                    "account.move.line",
                    domain,
                    ["debit:sum", "credit:sum"],
                    []
                )
                if result:
                    return result[0].get("debit", 0), result[0].get("credit", 0)
                return 0, 0

            @st.cache_data(ttl=1800)
            def get_invoices_without_payment(start_date, end_date, comp_id=None):
                """Get invoices in the period that are still unpaid."""
                domain = [
                    ("invoice_date", ">=", start_date),
                    ("invoice_date", "<=", end_date),
                    ("state", "=", "posted"),
                    ("payment_state", "in", ["not_paid", "partial"]),
                    ("move_type", "in", ["out_invoice", "in_invoice"])
                ]
                if comp_id:
                    domain.append(("company_id", "=", comp_id))
                return odoo_call(
                    "account.move", "search_read",
                    domain,
                    ["name", "invoice_date", "partner_id", "amount_total", "amount_residual", "move_type", "company_id"],
                    limit=500
                )

            @st.cache_data(ttl=1800)
            def get_costs_by_account_code(start_date, end_date, comp_id=None):
                """Get costs grouped by 2-digit account code prefix for 4* accounts."""
                domain = [
                    ("account_id.code", ">=", "400000"),
                    ("account_id.code", "<", "500000"),
                    ("date", ">=", start_date),
                    ("date", "<=", end_date),
                    ("parent_state", "=", "posted")
                ]
                if comp_id:
                    domain.append(("company_id", "=", comp_id))
                return odoo_read_group("account.move.line", domain, ["balance:sum"], ["account_id"])

            @st.cache_data(ttl=1800)
            def get_product_category_margins(start_date, end_date, comp_id=None):
                """Get sales revenue and cost of goods sold by product category for margin analysis."""
                # Get revenue by product (8* accounts)
                revenue_domain = [
                    ("account_id.code", ">=", "800000"),
                    ("account_id.code", "<", "900000"),
                    ("date", ">=", start_date),
                    ("date", "<=", end_date),
                    ("parent_state", "=", "posted"),
                    ("product_id", "!=", False)
                ]
                if comp_id:
                    revenue_domain.append(("company_id", "=", comp_id))

                revenue_data = odoo_call(
                    "account.move.line", "search_read",
                    revenue_domain,
                    ["product_id", "balance"],
                    limit=10000
                )

                # Get COGS by product (7* accounts)
                cogs_domain = [
                    ("account_id.code", ">=", "700000"),
                    ("account_id.code", "<", "800000"),
                    ("date", ">=", start_date),
                    ("date", "<=", end_date),
                    ("parent_state", "=", "posted"),
                    ("product_id", "!=", False)
                ]
                if comp_id:
                    cogs_domain.append(("company_id", "=", comp_id))

                cogs_data = odoo_call(
                    "account.move.line", "search_read",
                    cogs_domain,
                    ["product_id", "balance"],
                    limit=10000
                )

                return revenue_data, cogs_data

            @st.cache_data(ttl=1800)
            def get_vat_data(start_date, end_date, comp_id=None):
                """Get VAT/BTW data for the period.

                BTW accounts typically used in Odoo:
                - 1500xx: Te vorderen BTW (VAT receivable - input VAT)
                - 1510xx: Af te dragen BTW (VAT payable - output VAT)
                - 1520xx: BTW verrekenrekening
                """
                # Get all VAT-related account move lines
                # Search for accounts with 'BTW' or 'VAT' in the name
                vat_domain = [
                    ("date", ">=", start_date),
                    ("date", "<=", end_date),
                    ("parent_state", "=", "posted"),
                    "|", "|", "|",
                    ("account_id.code", "like", "15%"),  # Common BTW accounts
                    ("account_id.name", "ilike", "BTW"),
                    ("account_id.name", "ilike", "VAT"),
                    ("account_id.name", "ilike", "belasting")
                ]
                if comp_id:
                    vat_domain.append(("company_id", "=", comp_id))

                return odoo_read_group(
                    "account.move.line",
                    vat_domain,
                    ["debit:sum", "credit:sum", "balance:sum"],
                    ["account_id"]
                )

            @st.cache_data(ttl=1800)
            def get_vat_details(start_date, end_date, comp_id=None):
                """Get detailed VAT/BTW transactions for the period."""
                vat_domain = [
                    ("date", ">=", start_date),
                    ("date", "<=", end_date),
                    ("parent_state", "=", "posted"),
                    "|", "|", "|",
                    ("account_id.code", "like", "15%"),
                    ("account_id.name", "ilike", "BTW"),
                    ("account_id.name", "ilike", "VAT"),
                    ("account_id.name", "ilike", "belasting")
                ]
                if comp_id:
                    vat_domain.append(("company_id", "=", comp_id))

                return odoo_call(
                    "account.move.line", "search_read",
                    vat_domain,
                    ["date", "name", "account_id", "debit", "credit", "balance", "partner_id", "move_id"],
                    limit=500
                )

            def analyze_vat_with_ai(vat_current, vat_previous, period_label, prev_period_label, btw_is_monthly):
                """Use AI to analyze VAT deviations and provide insights."""
                if not get_openai_key():
                    return None, "Geen OpenAI API key geconfigureerd"

                # Prepare data summary for AI
                current_summary = []
                for item in vat_current:
                    account_info = item.get("account_id", [None, "Onbekend"])
                    account_name = account_info[1] if isinstance(account_info, list) and len(account_info) > 1 else str(account_info)
                    current_summary.append({
                        "account": account_name,
                        "debit": item.get("debit", 0),
                        "credit": item.get("credit", 0),
                        "balance": item.get("balance", 0)
                    })

                prev_summary = []
                for item in vat_previous:
                    account_info = item.get("account_id", [None, "Onbekend"])
                    account_name = account_info[1] if isinstance(account_info, list) and len(account_info) > 1 else str(account_info)
                    prev_summary.append({
                        "account": account_name,
                        "debit": item.get("debit", 0),
                        "credit": item.get("credit", 0),
                        "balance": item.get("balance", 0)
                    })

                # Calculate totals
                current_total_debit = sum(item.get("debit", 0) for item in vat_current)
                current_total_credit = sum(item.get("credit", 0) for item in vat_current)
                current_net = current_total_credit - current_total_debit

                prev_total_debit = sum(item.get("debit", 0) for item in vat_previous)
                prev_total_credit = sum(item.get("credit", 0) for item in vat_previous)
                prev_net = prev_total_credit - prev_total_debit

                period_type = "maand" if btw_is_monthly else "kwartaal"

                prompt = f"""Analyseer de volgende BTW-gegevens voor een Nederlands bedrijf en geef een korte, praktische analyse van afwijkingen.

**Periode:** {period_label} (BTW per {period_type})
**Vergelijkingsperiode:** {prev_period_label}

**Huidige periode BTW-data:**
{json.dumps(current_summary, indent=2)}
Totaal debet (voorbelasting): €{current_total_debit:,.2f}
Totaal credit (af te dragen): €{current_total_credit:,.2f}
Netto af te dragen: €{current_net:,.2f}

**Vorige periode BTW-data:**
{json.dumps(prev_summary, indent=2)}
Totaal debet (voorbelasting): €{prev_total_debit:,.2f}
Totaal credit (af te dragen): €{prev_total_credit:,.2f}
Netto af te dragen: €{prev_net:,.2f}

**Verschil:** €{current_net - prev_net:,.2f}

Geef een bondige analyse (max 5 bullet points) met:
1. Korte samenvatting van de BTW-positie
2. Belangrijkste afwijkingen t.o.v. vorige periode
3. Mogelijke oorzaken voor de afwijkingen
4. Aandachtspunten voor de BTW-aangifte
5. Eventuele risico's of actiepunten

Antwoord in het Nederlands en wees praktisch/actionable."""

                messages = [
                    {"role": "system", "content": "Je bent een ervaren fiscalist/boekhouder die BTW-analyses uitvoert voor Nederlandse bedrijven. Geef praktische, bondige analyses."},
                    {"role": "user", "content": prompt}
                ]

                return call_openai(messages)

            # =================================================================
            # LOAD DATA
            # =================================================================
            with st.spinner("📊 Data laden voor maandafsluiting..."):
                # Current period data
                current_revenue = get_period_revenue(period_start, period_end, fc_company_id)
                current_costs = get_period_costs(period_start, period_end, fc_company_id)
                current_profit = current_revenue - current_costs

                # Previous period data
                prev_revenue = get_period_revenue(prev_start, prev_end, fc_company_id)
                prev_costs = get_period_costs(prev_start, prev_end, fc_company_id)
                prev_profit = prev_revenue - prev_costs

                # Validation data
                unposted = get_unposted_entries(period_start, period_end, fc_company_id)
                unreconciled_rec, unreconciled_pay = get_unreconciled_items(fc_company_id)
                total_debit, total_credit = get_balance_check(period_end, fc_company_id)
                unpaid_invoices = get_invoices_without_payment(period_start, period_end, fc_company_id)

                # Cost component analysis data
                current_costs_by_account = get_costs_by_account_code(period_start, period_end, fc_company_id)
                prev_costs_by_account = get_costs_by_account_code(prev_start, prev_end, fc_company_id)

                # Product category margin data
                current_revenue_by_product, current_cogs_by_product = get_product_category_margins(period_start, period_end, fc_company_id)
                prev_revenue_by_product, prev_cogs_by_product = get_product_category_margins(prev_start, prev_end, fc_company_id)

                # BTW/VAT data
                current_vat_data = get_vat_data(btw_period_start, btw_period_end, fc_company_id)
                prev_vat_data = get_vat_data(btw_prev_start, btw_prev_end, fc_company_id)

            st.markdown("---")

            # =================================================================
            # KEY FINANCIAL METRICS
            # =================================================================
            st.subheader("💰 Financiële Kerncijfers")

            # Calculate deltas
            revenue_delta = current_revenue - prev_revenue
            revenue_pct = (revenue_delta / prev_revenue * 100) if prev_revenue else 0
            costs_delta = current_costs - prev_costs
            costs_pct = (costs_delta / prev_costs * 100) if prev_costs else 0
            profit_delta = current_profit - prev_profit
            profit_pct = (profit_delta / abs(prev_profit) * 100) if prev_profit else 0
            margin = (current_profit / current_revenue * 100) if current_revenue else 0

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric(
                    "📈 Omzet",
                    f"€{current_revenue:,.0f}",
                    delta=f"{revenue_pct:+.1f}% vs vorige maand"
                )
            with col2:
                st.metric(
                    "📉 Kosten",
                    f"€{current_costs:,.0f}",
                    delta=f"{costs_pct:+.1f}% vs vorige maand",
                    delta_color="inverse"
                )
            with col3:
                st.metric(
                    "💵 Resultaat",
                    f"€{current_profit:,.0f}",
                    delta=f"{profit_pct:+.1f}% vs vorige maand"
                )
            with col4:
                st.metric(
                    "📊 Marge",
                    f"{margin:.1f}%",
                    delta=f"€{profit_delta:+,.0f}"
                )

            st.markdown("---")

            # =================================================================
            # DATA VALIDATION CHECKS
            # =================================================================
            st.subheader("✅ Validatie Controles")

            validation_issues = []
            validation_warnings = []
            validation_ok = []

            # Check 1: Balance verification (Debit = Credit)
            balance_diff = abs(total_debit - total_credit)
            if balance_diff < 0.01:
                validation_ok.append(("Balans controle", "Debet = Credit ✓", f"Verschil: €{balance_diff:.2f}"))
            else:
                validation_issues.append(("Balans controle", f"Debet ≠ Credit!", f"Verschil: €{balance_diff:,.2f}"))

            # Check 2: Unposted entries
            if len(unposted) == 0:
                validation_ok.append(("Ongeboekte entries", "Geen ongeboekte boekingen ✓", "0 stuks"))
            else:
                validation_warnings.append(("Ongeboekte entries", f"{len(unposted)} ongeboekte boeking(en)", "Actie vereist"))

            # Check 3: Unpaid invoices from period
            unpaid_in_period = [inv for inv in unpaid_invoices if inv.get("move_type") == "out_invoice"]
            unpaid_bills = [inv for inv in unpaid_invoices if inv.get("move_type") == "in_invoice"]
            if len(unpaid_in_period) == 0:
                validation_ok.append(("Openstaande facturen", "Alle verkoopfacturen betaald ✓", "0 stuks"))
            else:
                total_unpaid = sum(inv.get("amount_residual", 0) for inv in unpaid_in_period)
                validation_warnings.append((
                    "Openstaande verkoop",
                    f"{len(unpaid_in_period)} facturen onbetaald",
                    f"€{total_unpaid:,.0f}"
                ))

            if len(unpaid_bills) == 0:
                validation_ok.append(("Openstaande inkoop", "Alle inkoopfacturen betaald ✓", "0 stuks"))
            else:
                total_unpaid_bills = sum(inv.get("amount_residual", 0) for inv in unpaid_bills)
                validation_warnings.append((
                    "Openstaande inkoop",
                    f"{len(unpaid_bills)} facturen onbetaald",
                    f"€{total_unpaid_bills:,.0f}"
                ))

            # Check 4: Large unreconciled items (>90 days old)
            old_date_threshold = datetime.now() - timedelta(days=90)
            old_receivables = [r for r in unreconciled_rec
                             if r.get("date") and datetime.strptime(r["date"], "%Y-%m-%d") < old_date_threshold]
            old_payables = [p for p in unreconciled_pay
                          if p.get("date") and datetime.strptime(p["date"], "%Y-%m-%d") < old_date_threshold]

            if len(old_receivables) == 0:
                validation_ok.append(("Oude debiteuren", "Geen vorderingen >90 dagen ✓", "0 stuks"))
            else:
                old_rec_total = sum(r.get("amount_residual", 0) for r in old_receivables)
                validation_issues.append((
                    "Oude debiteuren",
                    f"{len(old_receivables)} vorderingen >90 dagen",
                    f"€{old_rec_total:,.0f}"
                ))

            if len(old_payables) == 0:
                validation_ok.append(("Oude crediteuren", "Geen schulden >90 dagen ✓", "0 stuks"))
            else:
                old_pay_total = sum(abs(p.get("amount_residual", 0)) for p in old_payables)
                validation_warnings.append((
                    "Oude crediteuren",
                    f"{len(old_payables)} schulden >90 dagen",
                    f"€{old_pay_total:,.0f}"
                ))

            # Check 5: Major cost components booked check
            # Group costs by 2-digit prefix
            current_costs_grouped = {}
            for item in current_costs_by_account:
                account_info = item.get("account_id")
                if account_info and len(account_info) >= 2:
                    account_code = str(account_info[1]).split()[0] if isinstance(account_info[1], str) else str(account_info[0])
                    # Extract first 2 digits from account code
                    if len(account_code) >= 2:
                        prefix = account_code[:2]
                        current_costs_grouped[prefix] = current_costs_grouped.get(prefix, 0) + item.get("balance", 0)

            # Check for major cost components
            major_cost_components = {
                "40": "Personeelskosten (salarissen)",
                "48": "Afschrijvingen",
                "46": "Overige bedrijfskosten (incl. management fee)"
            }
            missing_components = []
            booked_components = []

            for prefix, name in major_cost_components.items():
                amount = current_costs_grouped.get(prefix, 0)
                if abs(amount) < 100:  # Less than €100 considered as not booked
                    missing_components.append((prefix, name))
                else:
                    booked_components.append((prefix, name, amount))

            if missing_components:
                missing_names = ", ".join([name for _, name in missing_components])
                validation_warnings.append((
                    "Kostencomponenten",
                    f"Mogelijk niet geboekt: {missing_names}",
                    f"{len(missing_components)} component(en)"
                ))
            else:
                validation_ok.append(("Kostencomponenten", "Alle grote kostencomponenten geboekt ✓", f"{len(booked_components)} geverifieerd"))

            # Check 6: GL account variances in 4* range (excluding 48, 49)
            # Group previous period costs
            prev_costs_grouped = {}
            for item in prev_costs_by_account:
                account_info = item.get("account_id")
                if account_info and len(account_info) >= 2:
                    account_code = str(account_info[1]).split()[0] if isinstance(account_info[1], str) else str(account_info[0])
                    if len(account_code) >= 2:
                        prefix = account_code[:2]
                        prev_costs_grouped[prefix] = prev_costs_grouped.get(prefix, 0) + item.get("balance", 0)

            # Check for large variances (>30%) on 40-47 accounts
            cost_variances = []
            for prefix in ["40", "41", "42", "43", "44", "45", "46", "47"]:
                current_amount = current_costs_grouped.get(prefix, 0)
                prev_amount = prev_costs_grouped.get(prefix, 0)

                if prev_amount != 0:
                    variance_pct = ((current_amount - prev_amount) / abs(prev_amount)) * 100
                    variance_abs = current_amount - prev_amount
                    # Flag if variance > 30% and absolute variance > €500
                    if abs(variance_pct) > 30 and abs(variance_abs) > 500:
                        category_name = CATEGORY_TRANSLATIONS.get(prefix, f"Categorie {prefix}")
                        cost_variances.append({
                            "prefix": prefix,
                            "name": category_name,
                            "current": current_amount,
                            "previous": prev_amount,
                            "variance_pct": variance_pct,
                            "variance_abs": variance_abs
                        })
                elif current_amount > 500:  # New significant cost this period
                    category_name = CATEGORY_TRANSLATIONS.get(prefix, f"Categorie {prefix}")
                    cost_variances.append({
                        "prefix": prefix,
                        "name": category_name,
                        "current": current_amount,
                        "previous": 0,
                        "variance_pct": 100,
                        "variance_abs": current_amount
                    })

            if cost_variances:
                # Sort by absolute variance
                cost_variances.sort(key=lambda x: abs(x["variance_abs"]), reverse=True)
                top_variances = cost_variances[:3]  # Top 3 variances
                variance_summary = ", ".join([f"{v['name']} ({v['variance_pct']:+.0f}%)" for v in top_variances])
                validation_warnings.append((
                    "Kostenvarianties (4*)",
                    f"Grote afwijkingen: {variance_summary}",
                    f"{len(cost_variances)} categorie(ën)"
                ))
            else:
                validation_ok.append(("Kostenvarianties (4*)", "Geen grote afwijkingen op 40-47 rekeningen ✓", "Binnen norm"))

            # Check 7: Product category margin variances
            # Aggregate by product category
            def aggregate_by_category(revenue_data, cogs_data):
                """Aggregate revenue and COGS by product category."""
                # Get unique product IDs
                product_ids = set()
                for item in revenue_data:
                    if item.get("product_id"):
                        product_ids.add(item["product_id"][0] if isinstance(item["product_id"], list) else item["product_id"])
                for item in cogs_data:
                    if item.get("product_id"):
                        product_ids.add(item["product_id"][0] if isinstance(item["product_id"], list) else item["product_id"])

                # Get product categories
                product_categories = {}
                if product_ids:
                    products = odoo_call(
                        "product.product", "search_read",
                        [["id", "in", list(product_ids)]],
                        ["id", "categ_id"],
                        limit=len(product_ids) + 100,
                        include_archived=True
                    )
                    for p in products:
                        categ = p.get("categ_id")
                        if categ:
                            categ_name = categ[1] if isinstance(categ, list) and len(categ) > 1 else "Onbekend"
                            product_categories[p["id"]] = categ_name

                # Aggregate by category
                category_data = {}
                for item in revenue_data:
                    if item.get("product_id"):
                        pid = item["product_id"][0] if isinstance(item["product_id"], list) else item["product_id"]
                        categ = product_categories.get(pid, "Overig")
                        if categ not in category_data:
                            category_data[categ] = {"revenue": 0, "cogs": 0}
                        category_data[categ]["revenue"] += -item.get("balance", 0)  # Revenue is negative in balance

                for item in cogs_data:
                    if item.get("product_id"):
                        pid = item["product_id"][0] if isinstance(item["product_id"], list) else item["product_id"]
                        categ = product_categories.get(pid, "Overig")
                        if categ not in category_data:
                            category_data[categ] = {"revenue": 0, "cogs": 0}
                        category_data[categ]["cogs"] += item.get("balance", 0)  # COGS is positive in balance

                return category_data

            current_category_data = aggregate_by_category(current_revenue_by_product, current_cogs_by_product)
            prev_category_data = aggregate_by_category(prev_revenue_by_product, prev_cogs_by_product)

            # Calculate margins and check for variances
            margin_variances = []
            for categ, data in current_category_data.items():
                current_revenue_cat = data["revenue"]
                current_cogs_cat = data["cogs"]
                current_margin = ((current_revenue_cat - current_cogs_cat) / current_revenue_cat * 100) if current_revenue_cat > 0 else 0

                prev_data = prev_category_data.get(categ, {"revenue": 0, "cogs": 0})
                prev_revenue_cat = prev_data["revenue"]
                prev_cogs_cat = prev_data["cogs"]
                prev_margin = ((prev_revenue_cat - prev_cogs_cat) / prev_revenue_cat * 100) if prev_revenue_cat > 0 else 0

                margin_change = current_margin - prev_margin

                # Flag if margin changed by more than 10 percentage points and revenue > €1000
                if abs(margin_change) > 10 and current_revenue_cat > 1000:
                    margin_variances.append({
                        "category": categ,
                        "current_margin": current_margin,
                        "prev_margin": prev_margin,
                        "margin_change": margin_change,
                        "current_revenue": current_revenue_cat
                    })

            if margin_variances:
                # Sort by absolute margin change
                margin_variances.sort(key=lambda x: abs(x["margin_change"]), reverse=True)
                top_margin_changes = margin_variances[:3]
                margin_summary = ", ".join([
                    f"{v['category'][:20]} ({v['margin_change']:+.1f}pp)"
                    for v in top_margin_changes
                ])
                validation_warnings.append((
                    "Productcategorie marges",
                    f"Grote margewijzigingen: {margin_summary}",
                    f"{len(margin_variances)} categorie(ën)"
                ))
            else:
                validation_ok.append(("Productcategorie marges", "Geen grote margewijzigingen ✓", "Binnen norm"))

            # Display validation results
            col1, col2, col3 = st.columns(3)

            with col1:
                if validation_issues:
                    st.error(f"🚨 **{len(validation_issues)} Kritieke issue(s)**")
                    for name, issue, detail in validation_issues:
                        st.markdown(f"- **{name}**: {issue} ({detail})")
                else:
                    st.success("✅ Geen kritieke issues gevonden")

            with col2:
                if validation_warnings:
                    st.warning(f"⚠️ **{len(validation_warnings)} Waarschuwing(en)**")
                    for name, warning, detail in validation_warnings:
                        st.markdown(f"- **{name}**: {warning} ({detail})")
                else:
                    st.success("✅ Geen waarschuwingen")

            with col3:
                st.success(f"✅ **{len(validation_ok)} Controle(s) geslaagd**")
                with st.expander("Details"):
                    for name, status, detail in validation_ok:
                        st.markdown(f"- **{name}**: {status}")

            st.markdown("---")

            # =================================================================
            # COST COMPONENT DETAILS
            # =================================================================
            st.subheader("💼 Kostencomponenten Analyse")

            with st.expander("📊 Details Kostencomponenten (40-49 rekeningen)", expanded=False):
                # Show cost components table
                cost_components_data = []
                for prefix in ["40", "41", "42", "43", "44", "45", "46", "47", "48", "49"]:
                    current_amount = current_costs_grouped.get(prefix, 0)
                    prev_amount = prev_costs_grouped.get(prefix, 0)
                    variance = current_amount - prev_amount
                    variance_pct = ((variance / abs(prev_amount)) * 100) if prev_amount != 0 else (100 if current_amount != 0 else 0)

                    category_name = CATEGORY_TRANSLATIONS.get(prefix, f"Categorie {prefix}")
                    cost_components_data.append({
                        "Code": prefix,
                        "Categorie": category_name,
                        f"Huidig ({period_label})": f"€{current_amount:,.0f}",
                        f"Vorig ({prev_period_label})": f"€{prev_amount:,.0f}",
                        "Verschil": f"€{variance:+,.0f}",
                        "Verschil %": f"{variance_pct:+.1f}%"
                    })

                df_cost_components = pd.DataFrame(cost_components_data)
                st.dataframe(df_cost_components, use_container_width=True, hide_index=True)

                # Highlight major cost components status
                st.markdown("**Grote kostencomponenten status:**")
                for prefix, name in major_cost_components.items():
                    amount = current_costs_grouped.get(prefix, 0)
                    if abs(amount) >= 100:
                        st.markdown(f"- ✅ **{name}**: €{amount:,.0f} geboekt")
                    else:
                        st.markdown(f"- ⚠️ **{name}**: Niet of minimaal geboekt (€{amount:,.0f})")

            # =================================================================
            # COST VARIANCE DETAILS (4* excl. 48, 49)
            # =================================================================
            with st.expander("📉 Details Kostenvarianties (40-47 rekeningen)", expanded=False):
                if cost_variances:
                    variance_table_data = []
                    for v in cost_variances:
                        variance_table_data.append({
                            "Code": v["prefix"],
                            "Categorie": v["name"],
                            "Huidig": f"€{v['current']:,.0f}",
                            "Vorig": f"€{v['previous']:,.0f}",
                            "Verschil": f"€{v['variance_abs']:+,.0f}",
                            "Verschil %": f"{v['variance_pct']:+.1f}%"
                        })
                    df_variances = pd.DataFrame(variance_table_data)
                    st.warning(f"⚠️ {len(cost_variances)} categorie(ën) met grote afwijking (>30% en >€500)")
                    st.dataframe(df_variances, use_container_width=True, hide_index=True)
                else:
                    st.success("✅ Geen grote kostenvarianties gevonden op 40-47 rekeningen")

            # =================================================================
            # PRODUCT CATEGORY MARGIN DETAILS
            # =================================================================
            with st.expander("📦 Details Productcategorie Marges", expanded=False):
                if current_category_data:
                    margin_table_data = []
                    for categ, data in sorted(current_category_data.items(), key=lambda x: x[1]["revenue"], reverse=True):
                        current_revenue_cat = data["revenue"]
                        current_cogs_cat = data["cogs"]
                        current_margin = ((current_revenue_cat - current_cogs_cat) / current_revenue_cat * 100) if current_revenue_cat > 0 else 0

                        prev_data = prev_category_data.get(categ, {"revenue": 0, "cogs": 0})
                        prev_revenue_cat = prev_data["revenue"]
                        prev_margin = ((prev_revenue_cat - prev_data["cogs"]) / prev_revenue_cat * 100) if prev_revenue_cat > 0 else 0

                        margin_change = current_margin - prev_margin

                        if current_revenue_cat > 100:  # Only show categories with meaningful revenue
                            margin_table_data.append({
                                "Categorie": categ[:30] if len(categ) > 30 else categ,
                                "Omzet": f"€{current_revenue_cat:,.0f}",
                                "Kostprijs": f"€{current_cogs_cat:,.0f}",
                                "Marge %": f"{current_margin:.1f}%",
                                "Vorige marge %": f"{prev_margin:.1f}%",
                                "Verandering": f"{margin_change:+.1f}pp"
                            })

                    if margin_table_data:
                        df_margins = pd.DataFrame(margin_table_data)
                        st.dataframe(df_margins, use_container_width=True, hide_index=True)

                        # Show categories with big margin changes
                        if margin_variances:
                            st.warning(f"⚠️ {len(margin_variances)} categorie(ën) met margewijziging >10 procentpunt:")
                            for v in margin_variances[:5]:
                                direction = "gestegen" if v["margin_change"] > 0 else "gedaald"
                                st.markdown(f"- **{v['category'][:30]}**: {v['prev_margin']:.1f}% → {v['current_margin']:.1f}% ({direction} met {abs(v['margin_change']):.1f}pp)")
                    else:
                        st.info("Geen productcategorieën met significante omzet gevonden")
                else:
                    st.info("Geen productcategorie data beschikbaar voor deze periode")

            st.markdown("---")

            # =================================================================
            # TREND ANALYSIS
            # =================================================================
            st.subheader("📈 Trend Analyse")

            # Get last 6 months of data for trend
            trend_data = []
            for i in range(6):
                if close_month - i > 0:
                    t_year = close_year
                    t_month = close_month - i
                else:
                    t_year = close_year - 1
                    t_month = 12 + (close_month - i)

                t_start = f"{t_year}-{t_month:02d}-01"
                t_end_day = monthrange(t_year, t_month)[1]
                t_end = f"{t_year}-{t_month:02d}-{t_end_day:02d}"

                t_revenue = get_period_revenue(t_start, t_end, fc_company_id)
                t_costs = get_period_costs(t_start, t_end, fc_company_id)
                t_profit = t_revenue - t_costs

                trend_data.append({
                    "Maand": f"{month_names[t_month - 1][:3]} {t_year}",
                    "Omzet": t_revenue,
                    "Kosten": t_costs,
                    "Resultaat": t_profit,
                    "sort_key": f"{t_year}{t_month:02d}"
                })

            # Reverse to show oldest first
            trend_data = sorted(trend_data, key=lambda x: x["sort_key"])

            df_trend = pd.DataFrame(trend_data)

            # Create trend chart
            fig_trend = go.Figure()
            fig_trend.add_trace(go.Scatter(
                x=df_trend["Maand"],
                y=df_trend["Omzet"],
                name="Omzet",
                mode="lines+markers",
                line=dict(color="#2ecc71", width=3),
                marker=dict(size=8)
            ))
            fig_trend.add_trace(go.Scatter(
                x=df_trend["Maand"],
                y=df_trend["Kosten"],
                name="Kosten",
                mode="lines+markers",
                line=dict(color="#e74c3c", width=3),
                marker=dict(size=8)
            ))
            fig_trend.add_trace(go.Bar(
                x=df_trend["Maand"],
                y=df_trend["Resultaat"],
                name="Resultaat",
                marker_color=["#27ae60" if r >= 0 else "#c0392b" for r in df_trend["Resultaat"]],
                opacity=0.6
            ))
            fig_trend.update_layout(
                title="Omzet, Kosten & Resultaat - Laatste 6 Maanden",
                xaxis_title="Maand",
                yaxis_title="Bedrag (€)",
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_trend, use_container_width=True)

            # Trend statistics
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**📊 Periode Statistieken**")
                avg_revenue = df_trend["Omzet"].mean()
                avg_costs = df_trend["Kosten"].mean()
                avg_profit = df_trend["Resultaat"].mean()
                st.markdown(f"- Gemiddelde omzet: **€{avg_revenue:,.0f}**/maand")
                st.markdown(f"- Gemiddelde kosten: **€{avg_costs:,.0f}**/maand")
                st.markdown(f"- Gemiddeld resultaat: **€{avg_profit:,.0f}**/maand")

            with col2:
                st.markdown("**📈 Huidige Maand vs Gemiddelde**")
                rev_vs_avg = ((current_revenue - avg_revenue) / avg_revenue * 100) if avg_revenue else 0
                cost_vs_avg = ((current_costs - avg_costs) / avg_costs * 100) if avg_costs else 0
                profit_vs_avg = ((current_profit - avg_profit) / abs(avg_profit) * 100) if avg_profit else 0

                rev_color = "green" if rev_vs_avg >= 0 else "red"
                cost_color = "red" if cost_vs_avg > 0 else "green"
                profit_color = "green" if profit_vs_avg >= 0 else "red"

                st.markdown(f"- Omzet: :{rev_color}[{rev_vs_avg:+.1f}%] vs gemiddelde")
                st.markdown(f"- Kosten: :{cost_color}[{cost_vs_avg:+.1f}%] vs gemiddelde")
                st.markdown(f"- Resultaat: :{profit_color}[{profit_vs_avg:+.1f}%] vs gemiddelde")

            st.markdown("---")

            # =================================================================
            # BTW/VAT ANALYSIS
            # =================================================================
            st.subheader(f"🧾 BTW Analyse ({btw_period_label})")

            # Calculate BTW totals
            current_vat_debit = sum(item.get("debit", 0) for item in current_vat_data)
            current_vat_credit = sum(item.get("credit", 0) for item in current_vat_data)
            current_vat_net = current_vat_credit - current_vat_debit

            prev_vat_debit = sum(item.get("debit", 0) for item in prev_vat_data)
            prev_vat_credit = sum(item.get("credit", 0) for item in prev_vat_data)
            prev_vat_net = prev_vat_credit - prev_vat_debit

            vat_change = current_vat_net - prev_vat_net
            vat_change_pct = ((vat_change / abs(prev_vat_net)) * 100) if prev_vat_net != 0 else 0

            # BTW Metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric(
                    "📥 Voorbelasting",
                    f"€{current_vat_debit:,.0f}",
                    help="Te vorderen BTW (input VAT)"
                )
            with col2:
                st.metric(
                    "📤 Af te dragen",
                    f"€{current_vat_credit:,.0f}",
                    help="Af te dragen BTW (output VAT)"
                )
            with col3:
                st.metric(
                    "💶 Netto BTW",
                    f"€{current_vat_net:,.0f}",
                    delta=f"{vat_change_pct:+.1f}% vs {btw_prev_label}",
                    delta_color="inverse" if current_vat_net > 0 else "normal",
                    help="Positief = af te dragen, Negatief = te ontvangen"
                )
            with col4:
                # AI Analysis button
                if st.button("🤖 AI Analyse", key="btw_ai_analysis", help="Laat AI de BTW afwijkingen analyseren"):
                    st.session_state.show_btw_ai_analysis = True

            # Show AI Analysis if requested
            if st.session_state.get("show_btw_ai_analysis", False):
                with st.spinner("🤖 AI analyseert BTW data..."):
                    ai_response, ai_error = analyze_vat_with_ai(
                        current_vat_data,
                        prev_vat_data,
                        btw_period_label,
                        btw_prev_label,
                        btw_monthly
                    )

                if ai_error:
                    st.error(f"❌ AI Analyse fout: {ai_error}")
                elif ai_response:
                    with st.expander("🤖 AI BTW Analyse", expanded=True):
                        st.markdown(ai_response)
                        if st.button("🔄 Verberg analyse", key="hide_btw_analysis"):
                            st.session_state.show_btw_ai_analysis = False
                            st.rerun()

            # BTW Details expander
            with st.expander("📊 BTW Details per Rekening", expanded=False):
                if current_vat_data:
                    vat_table_data = []
                    for item in current_vat_data:
                        account_info = item.get("account_id", [None, "Onbekend"])
                        account_name = account_info[1] if isinstance(account_info, list) and len(account_info) > 1 else str(account_info)

                        # Find previous period data for same account
                        prev_item = next(
                            (p for p in prev_vat_data if p.get("account_id") == item.get("account_id")),
                            {"debit": 0, "credit": 0, "balance": 0}
                        )

                        current_balance = item.get("credit", 0) - item.get("debit", 0)
                        prev_balance = prev_item.get("credit", 0) - prev_item.get("debit", 0)
                        change = current_balance - prev_balance
                        change_pct = ((change / abs(prev_balance)) * 100) if prev_balance != 0 else 0

                        vat_table_data.append({
                            "Rekening": account_name,
                            "Debet": f"€{item.get('debit', 0):,.0f}",
                            "Credit": f"€{item.get('credit', 0):,.0f}",
                            "Saldo": f"€{current_balance:,.0f}",
                            f"Vorige ({btw_prev_label})": f"€{prev_balance:,.0f}",
                            "Verschil": f"€{change:+,.0f}",
                            "Verschil %": f"{change_pct:+.1f}%"
                        })

                    if vat_table_data:
                        df_vat = pd.DataFrame(vat_table_data)
                        st.dataframe(df_vat, use_container_width=True, hide_index=True)

                        # Summary
                        st.markdown(f"""
                        **Samenvatting BTW {btw_period_label}:**
                        - Totaal voorbelasting (debet): **€{current_vat_debit:,.0f}**
                        - Totaal af te dragen (credit): **€{current_vat_credit:,.0f}**
                        - **Netto {'af te dragen' if current_vat_net > 0 else 'te ontvangen'}: €{abs(current_vat_net):,.0f}**
                        - Verschil t.o.v. {btw_prev_label}: €{vat_change:+,.0f} ({vat_change_pct:+.1f}%)
                        """)
                    else:
                        st.info("Geen BTW-rekeningen gevonden voor deze periode")
                else:
                    st.info("Geen BTW data beschikbaar voor deze periode")

            # BTW Warning if large variance
            if abs(vat_change_pct) > 25 and abs(vat_change) > 500:
                st.warning(f"⚠️ **Grote BTW afwijking**: {vat_change_pct:+.1f}% (€{vat_change:+,.0f}) t.o.v. {btw_prev_label}. Controleer de onderliggende transacties.")

            st.markdown("---")

            # =================================================================
            # ITEMS REQUIRING ATTENTION
            # =================================================================
            st.subheader("⚠️ Aandachtspunten")

            attention_items = []

            # Large variances from previous month
            if abs(revenue_pct) > 20:
                attention_items.append({
                    "Type": "📈 Omzet",
                    "Beschrijving": f"Grote afwijking t.o.v. vorige maand ({revenue_pct:+.1f}%)",
                    "Bedrag": f"€{abs(revenue_delta):,.0f}",
                    "Status": "Onderzoeken"
                })

            if abs(costs_pct) > 20:
                attention_items.append({
                    "Type": "📉 Kosten",
                    "Beschrijving": f"Grote afwijking t.o.v. vorige maand ({costs_pct:+.1f}%)",
                    "Bedrag": f"€{abs(costs_delta):,.0f}",
                    "Status": "Onderzoeken"
                })

            # Negative profit
            if current_profit < 0:
                attention_items.append({
                    "Type": "💰 Resultaat",
                    "Beschrijving": "Negatief resultaat deze maand",
                    "Bedrag": f"€{current_profit:,.0f}",
                    "Status": "Kritiek"
                })

            # Unposted entries
            if unposted:
                for entry in unposted[:5]:  # Show max 5
                    attention_items.append({
                        "Type": "📝 Ongeboekt",
                        "Beschrijving": f"{entry.get('name', 'Onbekend')}",
                        "Bedrag": f"€{entry.get('amount_total', 0):,.0f}",
                        "Status": "Boeken"
                    })

            # Old receivables
            for rec in old_receivables[:5]:  # Show max 5
                partner_name = rec.get("partner_id", [None, "Onbekend"])[1] if isinstance(rec.get("partner_id"), list) else "Onbekend"
                attention_items.append({
                    "Type": "👥 Debiteur",
                    "Beschrijving": f"{partner_name} - >90 dagen oud",
                    "Bedrag": f"€{rec.get('amount_residual', 0):,.0f}",
                    "Status": "Incasso"
                })

            if attention_items:
                df_attention = pd.DataFrame(attention_items)
                st.dataframe(
                    df_attention,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Status": st.column_config.Column(width="small")
                    }
                )
            else:
                st.success("✅ Geen bijzondere aandachtspunten gevonden!")

            st.markdown("---")

            # =================================================================
            # PERIOD RECONCILIATION SUMMARY
            # =================================================================
            st.subheader("📑 Periode Afsluiting Samenvatting")

            summary_data = {
                "Categorie": [
                    "Omzet",
                    "Kostprijs verkopen (7*)",
                    "Bruto marge",
                    "Overige kosten (4* + 6*)",
                    "**Netto resultaat**"
                ],
                f"{period_label}": [
                    f"€{current_revenue:,.0f}",
                    "Incl. in kosten",
                    f"€{current_revenue - (current_costs * 0.6):,.0f}",  # Approx
                    "Incl. in kosten",
                    f"**€{current_profit:,.0f}**"
                ],
                f"{prev_period_label}": [
                    f"€{prev_revenue:,.0f}",
                    "Incl. in kosten",
                    f"€{prev_revenue - (prev_costs * 0.6):,.0f}",
                    "Incl. in kosten",
                    f"**€{prev_profit:,.0f}**"
                ],
                "Verschil": [
                    f"€{revenue_delta:+,.0f}",
                    "-",
                    f"€{(current_revenue - prev_revenue) - ((current_costs - prev_costs) * 0.6):+,.0f}",
                    "-",
                    f"**€{profit_delta:+,.0f}**"
                ]
            }
            df_summary = pd.DataFrame(summary_data)
            st.dataframe(df_summary, use_container_width=True, hide_index=True)

            st.markdown("---")

            # =================================================================
            # EXPORT FUNCTIONALITY
            # =================================================================
            st.subheader("📥 Export Rapport")

            col1, col2, col3 = st.columns(3)

            # Prepare export data
            export_data = {
                "report_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "period": period_label,
                "company": close_company,
                "metrics": {
                    "revenue": current_revenue,
                    "costs": current_costs,
                    "profit": current_profit,
                    "margin_pct": margin
                },
                "comparison": {
                    "prev_period": prev_period_label,
                    "revenue_change_pct": revenue_pct,
                    "costs_change_pct": costs_pct,
                    "profit_change_pct": profit_pct
                },
                "validation": {
                    "critical_issues": len(validation_issues),
                    "warnings": len(validation_warnings),
                    "passed_checks": len(validation_ok),
                    "issues": validation_issues,
                    "warnings_detail": validation_warnings
                },
                "cost_components": {
                    "booked": [{"prefix": p, "name": n, "amount": a} for p, n, a in booked_components],
                    "missing": [{"prefix": p, "name": n} for p, n in missing_components]
                },
                "cost_variances": [
                    {"prefix": v["prefix"], "name": v["name"], "current": v["current"], "previous": v["previous"], "variance_pct": v["variance_pct"]}
                    for v in cost_variances
                ],
                "margin_variances": [
                    {"category": v["category"], "current_margin": v["current_margin"], "prev_margin": v["prev_margin"], "change": v["margin_change"]}
                    for v in margin_variances
                ],
                "attention_items_count": len(attention_items),
                "trend_data": [
                    {"month": t["Maand"], "revenue": t["Omzet"], "costs": t["Kosten"], "profit": t["Resultaat"]}
                    for t in trend_data
                ]
            }

            with col1:
                # JSON Export
                json_str = json.dumps(export_data, indent=2, default=str)
                st.download_button(
                    label="📄 Download JSON",
                    data=json_str,
                    file_name=f"financial_close_{close_year}_{close_month:02d}.json",
                    mime="application/json"
                )

            with col2:
                # CSV Export (trend data)
                csv_data = df_trend[["Maand", "Omzet", "Kosten", "Resultaat"]].to_csv(index=False)
                st.download_button(
                    label="📊 Download CSV (Trend)",
                    data=csv_data,
                    file_name=f"financial_close_trend_{close_year}_{close_month:02d}.csv",
                    mime="text/csv"
                )

            with col3:
                # Summary report as text
                report_text = f"""
MAANDAFSLUITING RAPPORT
========================
Rapport datum: {datetime.now().strftime("%Y-%m-%d %H:%M")}
Periode: {period_label}
Entiteit: {close_company}

FINANCIËLE KERNCIJFERS
----------------------
Omzet:      €{current_revenue:,.0f} ({revenue_pct:+.1f}% vs vorige maand)
Kosten:     €{current_costs:,.0f} ({costs_pct:+.1f}% vs vorige maand)
Resultaat:  €{current_profit:,.0f} ({profit_pct:+.1f}% vs vorige maand)
Marge:      {margin:.1f}%

VALIDATIE STATUS
----------------
Kritieke issues:  {len(validation_issues)}
Waarschuwingen:   {len(validation_warnings)}
Geslaagd:         {len(validation_ok)}

AANDACHTSPUNTEN
---------------
Aantal items: {len(attention_items)}

{''.join([f"- {item['Type']}: {item['Beschrijving']} ({item['Bedrag']})" + chr(10) for item in attention_items])}

TREND (laatste 6 maanden)
-------------------------
{''.join([f"{t['Maand']}: Omzet €{t['Omzet']:,.0f}, Kosten €{t['Kosten']:,.0f}, Resultaat €{t['Resultaat']:,.0f}" + chr(10) for t in trend_data])}

---
Gegenereerd door LAB Groep Financial Dashboard
"""
                st.download_button(
                    label="📝 Download Rapport (TXT)",
                    data=report_text,
                    file_name=f"financial_close_report_{close_year}_{close_month:02d}.txt",
                    mime="text/plain"
                )

            # Show close status
            st.markdown("---")
            total_issues = len(validation_issues) + len(validation_warnings)
            if total_issues == 0:
                st.success(f"✅ **Maand {period_label} is gereed voor afsluiting!**")
            elif len(validation_issues) > 0:
                st.error(f"🚨 **Maand {period_label} kan niet worden afgesloten** - {len(validation_issues)} kritieke issue(s) gevonden")
            else:
                st.warning(f"⚠️ **Maand {period_label} kan worden afgesloten** met {len(validation_warnings)} waarschuwing(en)")

        # =================================================================
        # PASSWORD PROTECTION FLOW
        # =================================================================
        if not password_configured:
            # No password configured - show setup instructions
            st.warning("⚠️ **Wachtwoord niet geconfigureerd**")
            st.markdown("""
            De Maandafsluiting functie vereist een wachtwoord voor toegang.

            **Configuratie instructies:**

            1. **Streamlit Cloud / Secrets:**
               Voeg toe aan je `secrets.toml` bestand:
               ```toml
               FINANCIAL_CLOSE_PASSWORD = "jouw_veilige_wachtwoord"
               ```

            2. **Environment Variable:**
               ```bash
               export FINANCIAL_CLOSE_PASSWORD="jouw_veilige_wachtwoord"
               ```

            3. **Lokaal (.streamlit/secrets.toml):**
               Maak een bestand `.streamlit/secrets.toml` aan met:
               ```toml
               FINANCIAL_CLOSE_PASSWORD = "jouw_veilige_wachtwoord"
               ```

            Na configuratie, herstart de applicatie.
            """)
            st.info("💡 Alle andere dashboard functionaliteit blijft normaal beschikbaar.")

        elif st.session_state.financial_close_authenticated:
            # Already authenticated - show content
            show_financial_close_content()

        else:
            # Password configured but not yet authenticated - show login form
            st.markdown("### 🔐 Authenticatie Vereist")
            st.markdown("Voer het wachtwoord in om toegang te krijgen tot de Maandafsluiting.")

            password_input = st.text_input(
                "Wachtwoord",
                type="password",
                key="fc_password_input",
                help="Voer het Maandafsluiting wachtwoord in"
            )

            col1, col2 = st.columns([1, 4])
            with col1:
                if st.button("🔓 Inloggen", type="primary"):
                    is_valid, error = verify_financial_close_password(password_input)
                    if is_valid:
                        st.session_state.financial_close_authenticated = True
                        st.rerun()
                    else:
                        st.error("❌ Onjuist wachtwoord. Probeer opnieuw.")

            st.markdown("---")
            st.info("💡 Het wachtwoord is geconfigureerd door de beheerder. Neem contact op als je toegang nodig hebt.")

if __name__ == "__main__":
    main()
