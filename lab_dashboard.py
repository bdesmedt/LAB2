"""
LAB Groep Financial Dashboard v18
=================================
Wijzigingen t.o.v. v17:
- 🔐 Directors Mode toegevoegd
  * Wachtwoord-beveiligde toegang tot externe LAB entiteiten
  * 3 nieuwe entiteiten: LAB Colour the World, MT Paints, Juloni Beheer
  * Aparte Odoo instanties met eigen API configuratie
  * Dynamische entiteitsselectie (basis vs uitgebreid)
- 🏢 Multi-instance support
  * Ondersteuning voor meerdere Odoo databases
  * Externe API keys via Streamlit secrets

Wijzigingen t.o.v. v16:
- 🎯 NIEUW: Budget 2026 tab
  * Automatisch geladen 2025 actuals per rekeninggroep
  * Interactieve groeiparameters via sliders (sidebar)
  * Automatische forecast berekening
  * Visuele vergelijking 2025 vs 2026 per maand
  * Kosten breakdown per groep
  * Variantie analyse (zodra 2026 actuals beschikbaar)
  * Scenario analyse (pessimistisch/basis/optimistisch)
  * Download functie (CSV export)

Wijzigingen t.o.v. v14:
- 📅 Omzet Week-op-Week jaarvergelijking in Overzicht tab
- 📊 Categorie Trend subtab in Producten tab

Eerder: Financial Forecast, BTW Analyse, Maandafsluiting, AI Chatbot, etc.
"""


# Fallback package installer voor Streamlit Cloud
import subprocess
import sys

def install_packages():
    packages = ['plotly', 'pandas', 'requests', 'folium', 'streamlit-folium', 'openpyxl']
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
# DIRECTORS MODE - EXTENDED ENTITIES
# =============================================================================

EXTENDED_ODOO_INSTANCES = {
    "lab_colour_the_world": {
        "name": "LAB Colour the World",
        "url": "https://labcolourtheworld.odoo.com/jsonrpc",
        "db": "labcolourtheworld",
        "uid": 2,
        "company_id": 100,
    },
    "mt_paints": {
        "name": "MT Paints",
        "url": "https://mtpaints.odoo.com/jsonrpc",
        "db": "mtpaints",
        "uid": 2,
        "company_id": 101,
    },
    "juloni_beheer": {
        "name": "Juloni Beheer",
        "url": "https://julonibeheer.odoo.com/jsonrpc",
        "db": "julonibeheer",
        "uid": 2,
        "company_id": 102,
    }
}

EXTENDED_COMPANIES = {
    100: "LAB Colour the World",
    101: "MT Paints",
    102: "Juloni Beheer",
}

def get_directors_password():
    """Get Directors password from secrets."""
    try:
        return st.secrets.get("DIRECTORS_PASSWORD", "")
    except:
        import os
        return os.environ.get("DIRECTORS_PASSWORD", "")

def get_extended_api_key(instance_key):
    """Get API key for extended Odoo instance."""
    secret_key = f"ODOO_API_KEY_{instance_key.upper()}"
    try:
        return st.secrets.get(secret_key, "")
    except:
        import os
        return os.environ.get(secret_key, "")

def verify_directors_password(input_password):
    """Verify directors password."""
    configured = get_directors_password()
    if not configured:
        return False, "no_password_configured"
    return (input_password == configured, None if input_password == configured else "invalid_password")

def is_directors_mode_active():
    """Check if directors mode is active."""
    return st.session_state.get("directors_authenticated", False)

def get_instance_for_company(company_id):
    """Get Odoo instance config for company_id."""
    for key, config in EXTENDED_ODOO_INSTANCES.items():
        if config["company_id"] == company_id:
            return key, config
    return None, None

def get_active_companies():
    """Get dict of active companies (includes extended if directors mode)."""
    companies = COMPANIES.copy()
    if is_directors_mode_active():
        companies.update(EXTENDED_COMPANIES)
    return companies

def odoo_call_extended(instance_key, model, method, domain, fields, limit=None, timeout=120):
    """Odoo JSON-RPC call for extended instances."""
    if instance_key not in EXTENDED_ODOO_INSTANCES:
        return []
    
    config = EXTENDED_ODOO_INSTANCES[instance_key]
    api_key = get_extended_api_key(instance_key)
    
    if not api_key:
        st.warning(f"API key niet geconfigureerd voor {config['name']}")
        return []
    
    args = [config["db"], config["uid"], api_key, model, method, [domain]]
    kwargs = {"fields": fields, "context": {"lang": "nl_NL"}}
    if limit:
        kwargs["limit"] = limit
    args.append(kwargs)
    
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {"service": "object", "method": "execute_kw", "args": args},
        "id": 1
    }
    
    try:
        response = requests.post(config["url"], json=payload, timeout=timeout)
        result = response.json()
        if "error" in result:
            return []
        return result.get("result", [])
    except:
        return []

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
def get_historical_bank_data_by_year(year, company_id=None):
    """Haal historische bankmutaties op per week voor een specifiek jaar"""
    from datetime import datetime, timedelta

    # Start en einddatum voor het jaar
    start_date = datetime(year, 1, 1).date()
    end_date = datetime(year, 12, 31).date()

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
        ["date", "<=", end_date.strftime("%Y-%m-%d")]
    ]
    if company_id:
        domain.append(["company_id", "=", company_id])

    movements = odoo_call(
        "account.move.line", "search_read",
        domain,
        ["date", "debit", "credit", "balance", "company_id", "partner_id", "name"],
        limit=20000
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
def get_product_sales_with_dates(year, company_id=None):
    """Haal verkopen per product op inclusief datum voor trend-analyse

    Inclusief creditnota's (out_refund) voor volledig beeld.
    """
    domain = [
        ["move_id.move_type", "in", ["out_invoice", "out_refund"]],
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
        ["product_id", "price_subtotal", "quantity", "company_id", "date"],
        limit=100000,
        include_archived=True
    )

@st.cache_data(ttl=300)
def get_pos_product_sales_with_dates(year, company_id=None):
    """Haal POS verkopen op met datum info voor trend-analyse"""
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

    # Map order_id -> date
    order_dates = {}
    for o in orders:
        date_str = o.get("date_order", "")
        order_dates[o["id"]] = date_str[:10] if date_str else ""

    order_ids = [o["id"] for o in orders]

    lines = odoo_call(
        "pos.order.line", "search_read",
        [["order_id", "in", order_ids]],
        ["product_id", "price_subtotal_incl", "price_subtotal", "qty", "order_id"],
        limit=100000,
        include_archived=True
    )

    # Voeg datum toe aan elke regel
    for line in lines:
        order_ref = line.get("order_id")
        order_id = order_ref[0] if isinstance(order_ref, list) else order_ref
        line["date"] = order_dates.get(order_id, "")

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
            ["display_type", "in", ["product", False]]
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
# FINANCIAL FORECAST MODULE
# =============================================================================
# This module provides financial forecasting capabilities including:
# - Manual forecast input with revenue, COGS, and expense categories
# - Pre-defined scenario templates (Conservative, Moderate, Aggressive)
# - Custom assumptions and variables
# - Actual vs Forecast comparison with visualizations
# - Data persistence for saving/loading forecasts
# - Export functionality (CSV, Excel)
#
# FUTURE CASHFLOW INTEGRATION:
# The data model is designed to accommodate future cashflow forecast integration.
# Forecast outputs can feed directly into a cashflow statement structure.
# Look for "CASHFLOW_HOOK" comments for integration points.
# =============================================================================

import os
from io import BytesIO

# Forecast storage directory
FORECAST_STORAGE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "forecasts")

# Default account mapping for forecast categories
# Users can customize this mapping in the Forecast tab
DEFAULT_ACCOUNT_MAPPING = {
    "revenue": {
        "name": "Omzet",
        "account_patterns": ["70", "71", "72", "73", "74"],  # Belgian/Dutch: 70-74 = revenue
        "sign_flip": True  # Revenue is typically negative in balance, flip to positive
    },
    "cogs": {
        "name": "Kostprijs Verkopen (COGS)",
        "account_patterns": ["60", "61"],  # 60-61 = purchases/COGS
        "sign_flip": False
    },
    "operating_expenses": {
        "name": "Operationele Kosten",
        "categories": {
            "61": "Diensten & Diverse Goederen",
            "62": "Bezoldigingen & Sociale Lasten",
            "63": "Afschrijvingen",
            "64": "Andere Bedrijfskosten",
            "65": "Financiële Kosten",
            "66": "Uitzonderlijke Kosten"
        }
    }
}

# Legacy expense categories (kept for backwards compatibility)
EXPENSE_CATEGORIES = {
    "61": "Diensten & Diverse Goederen",
    "62": "Bezoldigingen & Sociale Lasten",
    "63": "Afschrijvingen",
    "64": "Andere Bedrijfskosten",
    "65": "Financiële Kosten",
    "66": "Uitzonderlijke Kosten"
}

# =============================================================================
# DRAGGABLE MAPPING CONFIGURATION
# New financial report structure for forecasting
# =============================================================================

# Report categories with order and calculation rules
REPORT_CATEGORIES = {
    # SECTION 1: Revenue and Cost of Sales
    "netto_omzet": {
        "name": "Netto Omzet",
        "section": "revenue",
        "order": 1,
        "sign_flip": True,
        "account_patterns": [],  # Will be populated by user
        "is_subtotal": False
    },
    "kostprijs_omzet": {
        "name": "Kostprijs van de Omzet",
        "section": "revenue",
        "order": 2,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "prijsverschillen": {
        "name": "Prijsverschillen",
        "section": "revenue",
        "order": 3,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "overige_inkoopkosten": {
        "name": "Overige Inkoopkosten",
        "section": "revenue",
        "order": 4,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "voorraadaanpassingen": {
        "name": "Voorraadaanpassingen",
        "section": "revenue",
        "order": 5,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "bruto_omzet_resultaat": {
        "name": "Bruto Omzet Resultaat",
        "section": "revenue",
        "order": 6,
        "is_subtotal": True,
        "calculation": "netto_omzet - kostprijs_omzet - prijsverschillen - overige_inkoopkosten - voorraadaanpassingen"
    },

    # SECTION 2: Operating Expenses
    "lonen_salarissen": {
        "name": "Lonen & Salarissen",
        "section": "operating_expenses",
        "order": 10,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "overige_personele_kosten": {
        "name": "Overige Personele Kosten",
        "section": "operating_expenses",
        "order": 11,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "management_fee": {
        "name": "Management Fee",
        "section": "operating_expenses",
        "order": 12,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "huisvestingskosten": {
        "name": "Huisvestingskosten",
        "section": "operating_expenses",
        "order": 13,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "verkoopkosten": {
        "name": "Verkoopkosten",
        "section": "operating_expenses",
        "order": 14,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "automatiseringskosten": {
        "name": "Automatiseringskosten",
        "section": "operating_expenses",
        "order": 15,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "vervoerskosten": {
        "name": "Vervoerskosten",
        "section": "operating_expenses",
        "order": 16,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "kantoorkosten": {
        "name": "Kantoorkosten",
        "section": "operating_expenses",
        "order": 17,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "admin_accountantskosten": {
        "name": "Administratie & Accountantskosten",
        "section": "operating_expenses",
        "order": 18,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "algemene_kosten": {
        "name": "Algemene Kosten",
        "section": "operating_expenses",
        "order": 19,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "totaal_operationele_kosten": {
        "name": "Totaal Operationele Kosten",
        "section": "operating_expenses",
        "order": 20,
        "is_subtotal": True,
        "calculation": "lonen_salarissen + overige_personele_kosten + management_fee + huisvestingskosten + verkoopkosten + automatiseringskosten + vervoerskosten + kantoorkosten + admin_accountantskosten + algemene_kosten"
    },

    # SECTION 3: Other Income and Expenses
    "financieel_resultaat": {
        "name": "Financieel Resultaat",
        "section": "other_income_expenses",
        "order": 30,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "afschrijvingen": {
        "name": "Afschrijvingen",
        "section": "other_income_expenses",
        "order": 31,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "totaal_overige_lasten": {
        "name": "Totaal Overige Lasten en Opbrengsten",
        "section": "other_income_expenses",
        "order": 32,
        "is_subtotal": True,
        "calculation": "financieel_resultaat + afschrijvingen"
    },

    # SECTION 4: Result before tax
    "resultaat_voor_belasting": {
        "name": "Resultaat voor Belasting",
        "section": "result",
        "order": 40,
        "is_subtotal": True,
        "calculation": "bruto_omzet_resultaat - totaal_operationele_kosten - totaal_overige_lasten"
    },

    # SECTION 5: Taxes
    "belastingen": {
        "name": "Belastingen",
        "section": "taxes",
        "order": 50,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },

    # SECTION 6: Net Result
    "resultaat_na_belasting": {
        "name": "Resultaat na Belasting",
        "section": "result",
        "order": 60,
        "is_subtotal": True,
        "calculation": "resultaat_voor_belasting - belastingen"
    }
}

# Mapping storage file path
MAPPING_STORAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "account_mapping.json")

# New forecast expense categories based on REPORT_CATEGORIES
# These match the draggable mapping tool structure
FORECAST_EXPENSE_CATEGORIES = {
    # Omzet gerelateerd (niet Netto Omzet zelf, die staat apart)
    "kostprijs_omzet": "Kostprijs van de Omzet",
    "prijsverschillen": "Prijsverschillen",
    "overige_inkoopkosten": "Overige Inkoopkosten",
    "voorraadaanpassingen": "Voorraadaanpassingen",
    # Operationele kosten
    "lonen_salarissen": "Lonen & Salarissen",
    "overige_personele_kosten": "Overige Personele Kosten",
    "management_fee": "Management Fee",
    "huisvestingskosten": "Huisvestingskosten",
    "verkoopkosten": "Verkoopkosten",
    "automatiseringskosten": "Automatiseringskosten",
    "vervoerskosten": "Vervoerskosten",
    "kantoorkosten": "Kantoorkosten",
    "admin_accountantskosten": "Administratie & Accountantskosten",
    "algemene_kosten": "Algemene Kosten",
    # Overige lasten
    "financieel_resultaat": "Financieel Resultaat",
    "afschrijvingen": "Afschrijvingen",
    # Belastingen
    "belastingen": "Belastingen"
}

# Group categories for UI display
FORECAST_CATEGORY_GROUPS = {
    "cost_of_sales": {
        "name": "📦 Kostprijs & Inkoop",
        "categories": ["kostprijs_omzet", "prijsverschillen", "overige_inkoopkosten", "voorraadaanpassingen"],
        "subtotal_name": "Bruto Omzet Resultaat"
    },
    "operating_expenses": {
        "name": "⚙️ Operationele Kosten",
        "categories": ["lonen_salarissen", "overige_personele_kosten", "management_fee",
                      "huisvestingskosten", "verkoopkosten", "automatiseringskosten",
                      "vervoerskosten", "kantoorkosten", "admin_accountantskosten", "algemene_kosten"],
        "subtotal_name": "Totaal Operationele Kosten"
    },
    "other_expenses": {
        "name": "📊 Overige Lasten & Opbrengsten",
        "categories": ["financieel_resultaat", "afschrijvingen"],
        "subtotal_name": "Totaal Overige Lasten"
    },
    "taxes": {
        "name": "🏛️ Belastingen",
        "categories": ["belastingen"],
        "subtotal_name": "Belastingen"
    }
}

# Scenario templates with growth rates and expense multipliers
SCENARIO_TEMPLATES = {
    "conservative": {
        "name": "Conservatief",
        "description": "Lagere groei, hogere kostenramingen - veilige aanpak",
        "icon": "🐢",
        "revenue_growth_rate": 0.02,  # 2% groei
        "cogs_percentage": 0.65,  # 65% van omzet
        "expense_multiplier": 1.10,  # 10% hogere kosten
        "assumptions": {
            "customer_acquisition_rate": 0.05,  # 5% nieuwe klanten
            "average_transaction_value_growth": 0.01,  # 1% groei
            "churn_rate": 0.08,  # 8% verloop
            "seasonal_adjustment": 1.0,  # Geen seizoenscorrectie
            "inflation_rate": 0.03,  # 3% inflatie
        }
    },
    "moderate": {
        "name": "Gematigd",
        "description": "Gebalanceerde groei, realistische kostenramingen",
        "icon": "⚖️",
        "revenue_growth_rate": 0.05,  # 5% groei
        "cogs_percentage": 0.60,  # 60% van omzet
        "expense_multiplier": 1.0,  # Basis kosten
        "assumptions": {
            "customer_acquisition_rate": 0.10,  # 10% nieuwe klanten
            "average_transaction_value_growth": 0.03,  # 3% groei
            "churn_rate": 0.05,  # 5% verloop
            "seasonal_adjustment": 1.0,  # Geen seizoenscorrectie
            "inflation_rate": 0.025,  # 2.5% inflatie
        }
    },
    "aggressive": {
        "name": "Agressief",
        "description": "Hogere groeistreven, optimistische aannames",
        "icon": "🚀",
        "revenue_growth_rate": 0.10,  # 10% groei
        "cogs_percentage": 0.55,  # 55% van omzet
        "expense_multiplier": 0.95,  # 5% lagere kosten
        "assumptions": {
            "customer_acquisition_rate": 0.20,  # 20% nieuwe klanten
            "average_transaction_value_growth": 0.05,  # 5% groei
            "churn_rate": 0.03,  # 3% verloop
            "seasonal_adjustment": 1.0,  # Geen seizoenscorrectie
            "inflation_rate": 0.02,  # 2% inflatie
        }
    }
}

# Dutch month names for display
DUTCH_MONTHS = {
    1: "Januari", 2: "Februari", 3: "Maart", 4: "April",
    5: "Mei", 6: "Juni", 7: "Juli", 8: "Augustus",
    9: "September", 10: "Oktober", 11: "November", 12: "December"
}

def get_forecast_storage_path():
    """Get the path to the forecast storage directory, creating it if necessary"""
    if not os.path.exists(FORECAST_STORAGE_DIR):
        os.makedirs(FORECAST_STORAGE_DIR)
    return FORECAST_STORAGE_DIR

def save_forecast(forecast_data, filename=None):
    """
    Save a forecast to JSON file.

    Args:
        forecast_data: Dict containing forecast data
        filename: Optional filename, will be auto-generated if not provided

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        storage_path = get_forecast_storage_path()

        # Add metadata
        forecast_data["last_modified"] = datetime.now().isoformat()
        if "created_date" not in forecast_data:
            forecast_data["created_date"] = datetime.now().isoformat()

        # Generate filename if not provided
        if not filename:
            forecast_name = forecast_data.get("name", "forecast")
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in forecast_name)
            filename = f"{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        # Ensure .json extension
        if not filename.endswith(".json"):
            filename += ".json"

        filepath = os.path.join(storage_path, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(forecast_data, f, ensure_ascii=False, indent=2)

        return True, f"Forecast opgeslagen: {filename}"
    except Exception as e:
        return False, f"Fout bij opslaan: {str(e)}"

def load_forecast(filename):
    """
    Load a forecast from JSON file.

    Args:
        filename: Name of the file to load

    Returns:
        Tuple of (forecast_data: dict or None, error: str or None)
    """
    try:
        storage_path = get_forecast_storage_path()
        filepath = os.path.join(storage_path, filename)

        with open(filepath, "r", encoding="utf-8") as f:
            forecast_data = json.load(f)

        return forecast_data, None
    except Exception as e:
        return None, f"Fout bij laden: {str(e)}"

def list_saved_forecasts():
    """
    List all saved forecasts with metadata.

    Returns:
        List of dicts with forecast info (filename, name, created_date, scenario_type)
    """
    try:
        storage_path = get_forecast_storage_path()
        forecasts = []

        for filename in os.listdir(storage_path):
            if filename.endswith(".json"):
                filepath = os.path.join(storage_path, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    forecasts.append({
                        "filename": filename,
                        "name": data.get("name", filename),
                        "created_date": data.get("created_date", "Onbekend"),
                        "last_modified": data.get("last_modified", "Onbekend"),
                        "scenario_type": data.get("scenario_type", "custom"),
                        "company_id": data.get("company_id"),
                        "time_period_months": data.get("time_period_months", 12)
                    })
                except:
                    continue

        # Sort by last modified date (newest first)
        forecasts.sort(key=lambda x: x.get("last_modified", ""), reverse=True)
        return forecasts
    except Exception as e:
        return []

def delete_forecast(filename):
    """Delete a saved forecast file"""
    try:
        storage_path = get_forecast_storage_path()
        filepath = os.path.join(storage_path, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            return True, "Forecast verwijderd"
        return False, "Bestand niet gevonden"
    except Exception as e:
        return False, f"Fout bij verwijderen: {str(e)}"

def create_empty_forecast(company_id=None, time_period_months=12, start_month=None, start_year=None):
    """
    Create an empty forecast data structure.

    CASHFLOW_HOOK: This structure is designed to feed into cashflow forecasting.
    Revenue and expense timing can be adjusted for cashflow purposes by adding
    payment_timing fields (e.g., payment_delay_days for receivables/payables).

    Args:
        company_id: Optional company ID filter
        time_period_months: Number of months for the forecast
        start_month: Starting month (1-12), defaults to current month
        start_year: Starting year, defaults to current year
    """
    if start_month is None or start_year is None:
        start_date = datetime.now().replace(day=1)
    else:
        start_date = datetime(start_year, start_month, 1)

    # Generate monthly periods
    periods = []
    for i in range(time_period_months):
        month_date = start_date + timedelta(days=32 * i)
        month_date = month_date.replace(day=1)
        periods.append({
            "month": month_date.month,
            "year": month_date.year,
            "label": f"{DUTCH_MONTHS[month_date.month]} {month_date.year}",
            "date": month_date.strftime("%Y-%m-%d")
        })

    # Create expense structure for legacy categories (backwards compatibility)
    expense_categories = {}
    for code, name in EXPENSE_CATEGORIES.items():
        expense_categories[code] = {
            "name": name,
            "values": [0.0] * time_period_months,
            "growth_rate": 0.0,  # Per-category growth rate override
            "notes": ""
        }

    # Create NEW expense structure based on FORECAST_EXPENSE_CATEGORIES
    new_expense_categories = {}
    for code, name in FORECAST_EXPENSE_CATEGORIES.items():
        new_expense_categories[code] = {
            "name": name,
            "values": [0.0] * time_period_months,
            "growth_rate": 0.0,
            "notes": ""
        }

    forecast = {
        "name": "",
        "description": "",
        "scenario_type": "custom",
        "company_id": company_id,
        "time_period_months": time_period_months,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "start_year": start_year or datetime.now().year,
        "created_date": datetime.now().isoformat(),
        "last_modified": datetime.now().isoformat(),
        "periods": periods,

        # Revenue section (Netto Omzet)
        # CASHFLOW_HOOK: Add payment_terms field for AR aging simulation
        "revenue": {
            "values": [0.0] * time_period_months,
            "growth_rate": 0.0,
            "input_type": "absolute",  # 'absolute' or 'growth'
            "notes": ""
        },

        # NEW: Expense categories based on new report structure
        # Includes: kostprijs_omzet, prijsverschillen, overige_inkoopkosten, voorraadaanpassingen
        #           lonen_salarissen, overige_personele_kosten, management_fee, etc.
        #           financieel_resultaat, afschrijvingen, belastingen
        "expenses": new_expense_categories,

        # LEGACY: Cost of Goods Sold (kept for backwards compatibility)
        # CASHFLOW_HOOK: Add payment_terms for AP aging simulation
        "cogs": {
            "values": [0.0] * time_period_months,
            "percentage_of_revenue": 0.60,
            "input_type": "percentage",  # 'absolute' or 'percentage'
            "notes": ""
        },

        # LEGACY: Operating Expenses by category (kept for backwards compatibility)
        "operating_expenses": expense_categories,

        # Capital Expenditures
        # CASHFLOW_HOOK: CapEx directly impacts cash and can be scheduled
        "capex": {
            "values": [0.0] * time_period_months,
            "notes": ""
        },

        # Other Income/Expenses
        "other_income": {
            "values": [0.0] * time_period_months,
            "notes": ""
        },
        "other_expenses": {
            "values": [0.0] * time_period_months,
            "notes": ""
        },

        # Assumptions
        "assumptions": {
            "customer_acquisition_rate": 0.10,
            "average_transaction_value": 0.0,
            "average_transaction_value_growth": 0.03,
            "churn_rate": 0.05,
            "seasonal_factors": [1.0] * 12,  # Monthly adjustment factors
            "inflation_rate": 0.025,
            "monthly_growth_modifiers": [0.0] * time_period_months,
            "notes": ""
        },

        # One-time events
        "one_time_events": [],  # List of {month_index, amount, description, type: 'income'/'expense'}

        # Calculated fields (populated by calculate_forecast_metrics)
        "calculated": {}
    }

    return forecast

def apply_scenario_template(forecast, scenario_key, base_revenue=None, base_expenses=None,
                           custom_growth_rate=None, custom_cogs_percentage=None, custom_expense_multiplier=None):
    """
    Apply a scenario template to a forecast, optionally using base values.

    Args:
        forecast: Forecast dict to modify
        scenario_key: 'conservative', 'moderate', 'aggressive', or 'custom'
        base_revenue: Base monthly revenue (if None, uses existing or 0)
        base_expenses: Dict of base expenses by category (if None, estimates from revenue)
        custom_growth_rate: Override growth rate (decimal, e.g., 0.05 for 5%)
        custom_cogs_percentage: Override COGS percentage (decimal, e.g., 0.60 for 60%)
        custom_expense_multiplier: Override expense multiplier (e.g., 1.1 for +10%)

    Returns:
        Modified forecast dict
    """
    if scenario_key not in SCENARIO_TEMPLATES:
        return forecast

    template = SCENARIO_TEMPLATES[scenario_key]
    forecast["scenario_type"] = scenario_key

    # Get base revenue
    if base_revenue is None:
        base_revenue = forecast["revenue"]["values"][0] if forecast["revenue"]["values"][0] > 0 else 100000

    # Use custom values if provided, otherwise use template defaults
    growth_rate = custom_growth_rate if custom_growth_rate is not None else template["revenue_growth_rate"]
    cogs_percentage = custom_cogs_percentage if custom_cogs_percentage is not None else template["cogs_percentage"]
    multiplier = custom_expense_multiplier if custom_expense_multiplier is not None else template["expense_multiplier"]

    # Apply revenue with growth
    for i in range(len(forecast["revenue"]["values"])):
        forecast["revenue"]["values"][i] = base_revenue * ((1 + growth_rate) ** i)
    forecast["revenue"]["growth_rate"] = growth_rate * 100

    # Apply COGS as percentage of revenue
    forecast["cogs"]["percentage_of_revenue"] = cogs_percentage
    forecast["cogs"]["input_type"] = "percentage"
    for i in range(len(forecast["cogs"]["values"])):
        forecast["cogs"]["values"][i] = forecast["revenue"]["values"][i] * cogs_percentage

    # Apply expense multiplier to operating expenses
    base_expense_per_category = base_revenue * 0.05  # Rough estimate: 5% of revenue per category

    if base_expenses:
        for code, expense_data in forecast["operating_expenses"].items():
            if code in base_expenses:
                base = base_expenses[code]
            else:
                base = base_expense_per_category
            for i in range(len(expense_data["values"])):
                expense_data["values"][i] = base * multiplier * ((1 + template["assumptions"]["inflation_rate"]) ** (i / 12))
    else:
        for code, expense_data in forecast["operating_expenses"].items():
            for i in range(len(expense_data["values"])):
                expense_data["values"][i] = base_expense_per_category * multiplier * ((1 + template["assumptions"]["inflation_rate"]) ** (i / 12))

    # Apply assumptions
    for key, value in template["assumptions"].items():
        if key in forecast["assumptions"]:
            forecast["assumptions"][key] = value

    return forecast

def calculate_forecast_metrics(forecast):
    """
    Calculate derived metrics from forecast data.

    CASHFLOW_HOOK: Add net_cash_flow calculations here based on:
    - Revenue timing (payment terms)
    - Expense payment schedules
    - CapEx outlays
    - Working capital changes

    Returns:
        Dict with calculated metrics
    """
    periods = forecast.get("periods", [])
    num_periods = len(periods)

    if num_periods == 0:
        return {}

    revenue = forecast["revenue"]["values"]

    # Check if using new expense structure or legacy COGS
    use_new_structure = "expenses" in forecast and any(
        sum(cat.get("values", [])) > 0
        for cat in forecast.get("expenses", {}).values()
    )

    if use_new_structure:
        # NEW STRUCTURE: Calculate using the new expense categories
        expenses = forecast.get("expenses", {})

        # Cost of sales categories
        cost_of_sales_cats = ["kostprijs_omzet", "prijsverschillen", "overige_inkoopkosten", "voorraadaanpassingen"]
        cogs = [0.0] * num_periods
        for cat_code in cost_of_sales_cats:
            cat_data = expenses.get(cat_code, {}).get("values", [0.0] * num_periods)
            for i in range(min(len(cat_data), num_periods)):
                cogs[i] += cat_data[i]

        # Operating expenses categories
        opex_cats = ["lonen_salarissen", "overige_personele_kosten", "management_fee",
                     "huisvestingskosten", "verkoopkosten", "automatiseringskosten",
                     "vervoerskosten", "kantoorkosten", "admin_accountantskosten", "algemene_kosten"]
        opex_per_period = [0.0] * num_periods
        for cat_code in opex_cats:
            cat_data = expenses.get(cat_code, {}).get("values", [0.0] * num_periods)
            for i in range(min(len(cat_data), num_periods)):
                opex_per_period[i] += cat_data[i]

        # Other expenses (financieel resultaat, afschrijvingen)
        other_exp_cats = ["financieel_resultaat", "afschrijvingen"]
        other_expenses_new = [0.0] * num_periods
        for cat_code in other_exp_cats:
            cat_data = expenses.get(cat_code, {}).get("values", [0.0] * num_periods)
            for i in range(min(len(cat_data), num_periods)):
                other_expenses_new[i] += cat_data[i]

        # Taxes
        taxes = expenses.get("belastingen", {}).get("values", [0.0] * num_periods)

        # Depreciation for EBITDA calculation
        depreciation = expenses.get("afschrijvingen", {}).get("values", [0.0] * num_periods)

    else:
        # LEGACY STRUCTURE: Use old COGS and operating_expenses
        cogs = forecast["cogs"]["values"]

        # If COGS is percentage-based, calculate values
        if forecast["cogs"]["input_type"] == "percentage":
            cogs_pct = forecast["cogs"]["percentage_of_revenue"]
            cogs = [r * cogs_pct for r in revenue]

        # Sum all operating expenses per period
        opex_per_period = [0.0] * num_periods
        for category_data in forecast.get("operating_expenses", {}).values():
            for i, val in enumerate(category_data["values"]):
                if i < num_periods:
                    opex_per_period[i] += val

        other_expenses_new = [0.0] * num_periods
        taxes = [0.0] * num_periods
        depreciation = forecast.get("operating_expenses", {}).get("63", {}).get("values", [0.0] * num_periods)

    # Calculate metrics per period
    gross_profit = [revenue[i] - cogs[i] for i in range(num_periods)]
    gross_margin = [(gp / rev * 100) if rev > 0 else 0 for gp, rev in zip(gross_profit, revenue)]

    # Operating income (EBIT)
    ebit = [gross_profit[i] - opex_per_period[i] for i in range(num_periods)]
    ebit_margin = [(e / rev * 100) if rev > 0 else 0 for e, rev in zip(ebit, revenue)]

    # Add other income/expenses (from legacy structure)
    other_income = forecast.get("other_income", {}).get("values", [0.0] * num_periods)
    other_expenses_legacy = forecast.get("other_expenses", {}).get("values", [0.0] * num_periods)
    capex = forecast.get("capex", {}).get("values", [0.0] * num_periods)

    # Combine other expenses
    total_other_expenses = [other_expenses_new[i] + other_expenses_legacy[i] for i in range(num_periods)]

    # Net income before taxes and one-time events
    income_before_tax = [ebit[i] + other_income[i] - total_other_expenses[i] for i in range(num_periods)]

    # Net income after taxes
    net_income = [income_before_tax[i] - taxes[i] for i in range(num_periods)]

    # Apply one-time events
    one_time = forecast.get("one_time_events", [])
    for event in one_time:
        month_idx = event.get("month_index", 0)
        if 0 <= month_idx < num_periods:
            if event.get("type") == "income":
                net_income[month_idx] += event.get("amount", 0)
            else:
                net_income[month_idx] -= event.get("amount", 0)

    net_margin = [(ni / rev * 100) if rev > 0 else 0 for ni, rev in zip(net_income, revenue)]

    # EBITDA (add back depreciation)
    ebitda = [ebit[i] + depreciation[i] for i in range(num_periods)]
    ebitda_margin = [(eb / rev * 100) if rev > 0 else 0 for eb, rev in zip(ebitda, revenue)]

    # Cumulative totals
    cumulative_revenue = []
    cumulative_net_income = []
    running_rev = 0
    running_ni = 0
    for i in range(num_periods):
        running_rev += revenue[i]
        running_ni += net_income[i]
        cumulative_revenue.append(running_rev)
        cumulative_net_income.append(running_ni)

    # CASHFLOW_HOOK: Calculate operating cash flow
    # operating_cash_flow = net_income + depreciation - working_capital_changes
    # For now, simplified as: EBITDA - CapEx
    operating_cash_flow = [ebitda[i] - capex[i] for i in range(num_periods)]

    return {
        "revenue": revenue,
        "cogs": cogs,
        "gross_profit": gross_profit,
        "gross_margin": gross_margin,
        "operating_expenses": opex_per_period,
        "ebit": ebit,
        "ebit_margin": ebit_margin,
        "ebitda": ebitda,
        "ebitda_margin": ebitda_margin,
        "other_income": other_income,
        "other_expenses": total_other_expenses,
        "capex": capex,
        "net_income": net_income,
        "net_margin": net_margin,
        "depreciation": depreciation,
        "cumulative_revenue": cumulative_revenue,
        "cumulative_net_income": cumulative_net_income,
        "operating_cash_flow": operating_cash_flow,  # CASHFLOW_HOOK
        "total_revenue": sum(revenue),
        "total_gross_profit": sum(gross_profit),
        "total_ebitda": sum(ebitda),
        "total_net_income": sum(net_income),
        "avg_gross_margin": sum(gross_margin) / num_periods if num_periods > 0 else 0,
        "avg_net_margin": sum(net_margin) / num_periods if num_periods > 0 else 0
    }

def get_actual_data_for_comparison(company_id, start_date, num_months, revenue_patterns=None, cogs_patterns=None, expense_categories=None):
    """
    Fetch actual financial data from Odoo for comparison with forecast.

    Args:
        company_id: Company ID to filter by
        start_date: Start date string (YYYY-MM-DD)
        num_months: Number of months to fetch
        revenue_patterns: List of account prefixes for revenue (default: from DEFAULT_ACCOUNT_MAPPING)
        cogs_patterns: List of account prefixes for COGS (default: from DEFAULT_ACCOUNT_MAPPING)
        expense_categories: Dict of category code -> name for expenses (default: EXPENSE_CATEGORIES)

    Returns:
        Dict with actual data matching forecast structure
    """
    # Use defaults from mapping if not provided
    if revenue_patterns is None:
        revenue_patterns = DEFAULT_ACCOUNT_MAPPING["revenue"]["account_patterns"]
    if cogs_patterns is None:
        cogs_patterns = DEFAULT_ACCOUNT_MAPPING["cogs"]["account_patterns"]
    if expense_categories is None:
        expense_categories = EXPENSE_CATEGORIES

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = start + timedelta(days=32 * num_months)
        end = end.replace(day=1) - timedelta(days=1)

        # Build domain filters
        base_domain = [
            ["date", ">=", start_date],
            ["date", "<=", end.strftime("%Y-%m-%d")],
            ["parent_state", "=", "posted"]
        ]

        if company_id:
            base_domain.append(["company_id", "=", company_id])

        # Fetch revenue using configured account patterns
        revenue_data = []
        for pattern in revenue_patterns:
            revenue_domain = base_domain + [["account_id.code", "=like", f"{pattern}%"]]
            data = odoo_read_group(
                "account.move.line",
                revenue_domain,
                ["balance:sum"],
                ["date:month"]
            )
            revenue_data.extend(data)

        # Fetch COGS using configured account patterns
        cogs_data = []
        for pattern in cogs_patterns:
            cogs_domain = base_domain + [["account_id.code", "=like", f"{pattern}%"]]
            data = odoo_read_group(
                "account.move.line",
                cogs_domain,
                ["balance:sum"],
                ["date:month"]
            )
            cogs_data.extend(data)

        # Fetch operating expenses using configured categories
        expenses_by_category = {}
        for cat_code in expense_categories.keys():
            exp_domain = base_domain + [["account_id.code", "=like", f"{cat_code}%"]]
            exp_data = odoo_read_group(
                "account.move.line",
                exp_domain,
                ["balance:sum"],
                ["date:month"]
            )
            expenses_by_category[cat_code] = exp_data

        # Convert to monthly arrays
        months = []
        current = start
        for i in range(num_months):
            months.append(current.strftime("%B %Y"))
            current = (current + timedelta(days=32)).replace(day=1)

        # Helper to sum all values for a month (aggregates multiple entries from different account patterns)
        def get_month_value(data_list, month_str):
            total = 0
            for item in data_list:
                if item.get("date:month") == month_str:
                    total += item.get("balance:sum", 0)
            return total

        actual_revenue = []
        actual_cogs = []
        for month in months:
            # Revenue is negative in Odoo, flip sign
            actual_revenue.append(-get_month_value(revenue_data, month))
            actual_cogs.append(get_month_value(cogs_data, month))

        actual_expenses = {}
        for cat_code, cat_data in expenses_by_category.items():
            actual_expenses[cat_code] = [get_month_value(cat_data, m) for m in months]

        return {
            "revenue": actual_revenue,
            "cogs": actual_cogs,
            "operating_expenses": actual_expenses,
            "months": months
        }
    except Exception as e:
        st.error(f"Fout bij ophalen actuele data: {e}")
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def discover_account_groups(company_id, year):
    """
    Discover all account groups (2-digit prefixes) with their balances for a given year.
    This helps users understand what accounts exist and map them correctly.
    """
    try:
        start_date = f"{year}-01-01"
        end_date = f"{year}-12-31"

        domain = [
            ["date", ">=", start_date],
            ["date", "<=", end_date],
            ["parent_state", "=", "posted"]
        ]
        if company_id:
            domain.append(["company_id", "=", company_id])

        # Fetch all account move lines with account info
        data = odoo_read_group(
            "account.move.line",
            domain,
            ["balance:sum"],
            ["account_id"]
        )

        # Group by 2-digit prefix
        account_groups = {}
        for item in data:
            account = item.get("account_id")
            if account:
                account_code = str(account[1]).split()[0] if isinstance(account, (list, tuple)) else str(account)
                # Extract first 2 digits as group
                prefix = account_code[:2] if len(account_code) >= 2 else account_code
                balance = item.get("balance:sum", 0)

                if prefix not in account_groups:
                    account_groups[prefix] = {"balance": 0, "accounts": []}
                account_groups[prefix]["balance"] += balance
                account_groups[prefix]["accounts"].append(account)

        return account_groups
    except Exception as e:
        print(f"Error discovering account groups: {e}")
        return {}

def get_account_mapping():
    """Get the current account mapping from session_state or return defaults."""
    if "forecast_account_mapping" in st.session_state:
        return st.session_state.forecast_account_mapping
    return DEFAULT_ACCOUNT_MAPPING


# =============================================================================
# DRAGGABLE MAPPING FUNCTIONS
# =============================================================================

def get_all_accounts_with_details(company_id, year):
    """
    Fetch all accounts with their codes, names, and balances for a given year.
    Returns a list of accounts that can be assigned to report categories.
    Uses the existing discover_account_groups function and expands the data.
    """
    # Use the existing working function to get account groups
    account_groups = discover_account_groups(company_id, year)

    if not account_groups:
        return []

    accounts = []
    for prefix, info in account_groups.items():
        # Each account in the group
        for account in info.get("accounts", []):
            if account and isinstance(account, (list, tuple)) and len(account) >= 2:
                account_id = account[0]
                account_display = account[1]  # Format: "CODE Description"
                parts = account_display.split(" ", 1)
                code = parts[0] if parts else str(account_id)
                name = parts[1] if len(parts) > 1 else account_display

                # Check if already added (avoid duplicates)
                if not any(a["code"] == code for a in accounts):
                    accounts.append({
                        "id": account_id,
                        "code": code,
                        "name": name,
                        "display": f"{code} - {name[:50]}",
                        "balance": info.get("balance", 0) / max(len(info.get("accounts", [])), 1)  # Approximate
                    })

    # Sort by account code
    accounts.sort(key=lambda x: x["code"])
    return accounts


def save_draggable_mapping(mapping_data):
    """
    Save the draggable mapping configuration to a JSON file.

    Args:
        mapping_data: Dict with category keys and lists of account codes

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # Add metadata
        mapping_data["last_modified"] = datetime.now().isoformat()
        if "created_date" not in mapping_data:
            mapping_data["created_date"] = datetime.now().isoformat()

        with open(MAPPING_STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(mapping_data, f, ensure_ascii=False, indent=2)

        return True, "Mapping configuratie opgeslagen!"
    except Exception as e:
        return False, f"Fout bij opslaan: {str(e)}"


def load_draggable_mapping():
    """
    Load the draggable mapping configuration from JSON file.

    Returns:
        Dict with mapping data or empty dict if not found
    """
    try:
        if os.path.exists(MAPPING_STORAGE_FILE):
            with open(MAPPING_STORAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading mapping: {e}")
    return {}


def get_draggable_mapping():
    """
    Get the current draggable mapping from session_state or load from file.
    """
    if "draggable_mapping" not in st.session_state:
        # Try to load from file
        saved_mapping = load_draggable_mapping()
        if saved_mapping:
            st.session_state.draggable_mapping = saved_mapping
        else:
            # Initialize with empty mapping
            st.session_state.draggable_mapping = {
                "categories": {key: [] for key in REPORT_CATEGORIES.keys() if not REPORT_CATEGORIES[key].get("is_subtotal", False)},
                "unassigned": []
            }
    return st.session_state.draggable_mapping


def render_draggable_mapping_tool(company_id, year):
    """
    Render the mapping tool interface with two-column layout:
    - Left: Hierarchical report structure with categories
    - Right: Unmapped accounts panel with search

    Features a "Edit Mode" (Bewerk Modus) that collects changes without refreshing,
    then commits all changes at once for better performance.
    """
    # Get current mapping
    mapping = get_draggable_mapping()

    # =========================================================================
    # EDIT MODE STATE MANAGEMENT
    # =========================================================================
    # Initialize edit mode state
    if "mapping_edit_mode" not in st.session_state:
        st.session_state.mapping_edit_mode = False

    # Initialize pending changes (only used in edit mode)
    if "pending_adds" not in st.session_state:
        st.session_state.pending_adds = {}  # {category_key: [account_codes]}
    if "pending_removes" not in st.session_state:
        st.session_state.pending_removes = {}  # {category_key: [account_codes]}

    edit_mode = st.session_state.mapping_edit_mode
    pending_adds = st.session_state.pending_adds
    pending_removes = st.session_state.pending_removes

    # Count total pending changes
    total_pending_adds = sum(len(v) for v in pending_adds.values())
    total_pending_removes = sum(len(v) for v in pending_removes.values())
    total_pending = total_pending_adds + total_pending_removes

    # =========================================================================
    # EDIT MODE TOGGLE AND COMMIT/DISCARD BUTTONS
    # =========================================================================
    mode_col1, mode_col2, mode_col3, mode_col4 = st.columns([2, 1, 1, 1])

    with mode_col1:
        if edit_mode:
            st.markdown(f"### ✏️ **Bewerk Modus** - {total_pending} wijziging(en) pending")
        else:
            st.markdown("### 📊 Mapping Tool")

    with mode_col2:
        if not edit_mode:
            if st.button("✏️ Bewerk Modus", key="enter_edit_mode", type="primary", help="Activeer bewerk modus om wijzigingen te verzamelen zonder te refreshen"):
                st.session_state.mapping_edit_mode = True
                st.session_state.pending_adds = {}
                st.session_state.pending_removes = {}
                st.rerun()
        else:
            # Show pending changes summary
            if total_pending > 0:
                st.caption(f"➕ {total_pending_adds} toe te voegen")
                st.caption(f"➖ {total_pending_removes} te verwijderen")

    with mode_col3:
        if edit_mode:
            if st.button("✅ Commit", key="commit_changes", type="primary", disabled=total_pending == 0, help="Pas alle wijzigingen toe"):
                # Apply all pending adds
                for cat_key, codes in pending_adds.items():
                    if cat_key not in mapping["categories"]:
                        mapping["categories"][cat_key] = []
                    for code in codes:
                        if code not in mapping["categories"][cat_key]:
                            mapping["categories"][cat_key].append(code)

                # Apply all pending removes
                for cat_key, codes in pending_removes.items():
                    if cat_key in mapping["categories"]:
                        mapping["categories"][cat_key] = [
                            c for c in mapping["categories"][cat_key] if c not in codes
                        ]

                # Update session state
                st.session_state.draggable_mapping = mapping
                st.session_state.pending_adds = {}
                st.session_state.pending_removes = {}
                st.session_state.mapping_edit_mode = False
                st.success(f"✅ {total_pending} wijziging(en) toegepast!")
                st.rerun()

    with mode_col4:
        if edit_mode:
            if st.button("❌ Annuleer", key="discard_changes", help="Verwerp alle pending wijzigingen"):
                st.session_state.pending_adds = {}
                st.session_state.pending_removes = {}
                st.session_state.mapping_edit_mode = False
                st.rerun()

    if edit_mode:
        st.info("💡 **Bewerk Modus actief**: Wijzigingen worden verzameld maar niet direct toegepast. Klik op 'Commit' om alle wijzigingen in één keer toe te passen, of 'Annuleer' om te verwerpen.")
        st.markdown("---")

    # Fetch available accounts
    with st.spinner("Rekeningen ophalen..."):
        available_accounts = get_all_accounts_with_details(company_id, year)

    if not available_accounts:
        st.warning(f"Geen rekeningen gevonden voor jaar {year}.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Ververs", key="refresh_empty"):
                discover_account_groups.clear()
                st.rerun()
        return

    # Get list of already assigned account codes (including pending changes in edit mode)
    assigned_codes = set()
    for cat_key, cat_accounts in mapping.get("categories", {}).items():
        for acc_code in cat_accounts:
            assigned_codes.add(acc_code)

    # In edit mode: include pending adds as assigned, exclude pending removes
    if edit_mode:
        # Add pending adds to assigned (so they don't show in unassigned list)
        for cat_key, codes in pending_adds.items():
            for code in codes:
                assigned_codes.add(code)
        # Remove pending removes from assigned (so they show in unassigned list again)
        for cat_key, codes in pending_removes.items():
            for code in codes:
                assigned_codes.discard(code)

    # Filter unassigned accounts
    unassigned_accounts = [
        acc for acc in available_accounts
        if acc["code"] not in assigned_codes
    ]

    # Create account display mapping for lookup
    account_lookup = {acc["code"]: acc for acc in available_accounts}

    # =========================================================================
    # TWO-COLUMN LAYOUT: Report Structure (left) | Unmapped Accounts (right)
    # =========================================================================
    col_report, col_unmapped = st.columns([2, 1])

    # -------------------------------------------------------------------------
    # LEFT COLUMN: Hierarchical Report Structure
    # -------------------------------------------------------------------------
    with col_report:
        st.markdown("### 📊 Rapportage Structuur")

        # Search box for report categories
        search_cat = st.text_input("🔍 Zoek categorie...", key="search_category", placeholder="Zoek op naam...")

        # Define the hierarchical report structure
        report_structure = [
            {"key": "netto_omzet", "name": "Revenue (Netto Omzet)", "level": 0, "expandable": True},
            {"key": "kostprijs_omzet", "name": "Cost of Goods Sold", "level": 0, "expandable": True},
            {"key": None, "name": "Other Operating Income", "level": 1, "is_header": True},
            {"key": "overige_inkoopkosten", "name": "Overige Inkoopkosten", "level": 1, "expandable": True},
            {"key": "prijsverschillen", "name": "Prijsverschillen", "level": 1, "expandable": True},
            {"key": "voorraadaanpassingen", "name": "Voorraadaanpassingen", "level": 1, "expandable": True},
            {"key": None, "name": "Personnel", "level": 1, "is_header": True},
            {"key": "lonen_salarissen", "name": "Lonen & Salarissen", "level": 1, "expandable": True},
            {"key": "overige_personele_kosten", "name": "Overige Personele Kosten", "level": 1, "expandable": True},
            {"key": "management_fee", "name": "Management Fee", "level": 1, "expandable": True},
            {"key": None, "name": "Housing", "level": 1, "is_header": True},
            {"key": "huisvestingskosten", "name": "Huisvestingskosten", "level": 1, "expandable": True},
            {"key": None, "name": "Office", "level": 1, "is_header": True},
            {"key": "kantoorkosten", "name": "Kantoorkosten", "level": 1, "expandable": True},
            {"key": None, "name": "Car / Transport", "level": 1, "is_header": True},
            {"key": "vervoerskosten", "name": "Vervoerskosten", "level": 1, "expandable": True},
            {"key": None, "name": "Development / Marketing", "level": 1, "is_header": True},
            {"key": "verkoopkosten", "name": "Verkoopkosten", "level": 1, "expandable": True},
            {"key": None, "name": "Automation", "level": 1, "is_header": True},
            {"key": "automatiseringskosten", "name": "Automatiseringskosten", "level": 1, "expandable": True},
            {"key": None, "name": "General", "level": 1, "is_header": True},
            {"key": "algemene_kosten", "name": "Algemene Kosten", "level": 1, "expandable": True},
            {"key": "admin_accountantskosten", "name": "Administratie & Accountantskosten", "level": 1, "expandable": True},
            {"key": None, "name": "General Expenses", "level": 1, "is_subtotal": True},
            {"key": None, "name": "EBITDA", "level": 1, "is_subtotal": True},
            {"key": "financieel_resultaat", "name": "Financial Result", "level": 0, "expandable": True},
            {"key": "afschrijvingen", "name": "Depreciations", "level": 0, "expandable": True},
            {"key": "belastingen", "name": "Taxes", "level": 0, "expandable": True},
            {"key": None, "name": "Net Result", "level": 1, "is_subtotal": True},
        ]

        # Render each row in the report structure
        for item in report_structure:
            # Apply search filter
            if search_cat and search_cat.lower() not in item["name"].lower():
                continue

            indent = "　" * item.get("level", 0)  # Use wide space for indent
            cat_key = item.get("key")

            # Subtotal rows (not editable)
            if item.get("is_subtotal"):
                st.markdown(f"**{indent}{item['name']}**")
                continue

            # Header rows (not editable)
            if item.get("is_header"):
                st.markdown(f"{indent}**{item['name']}**")
                continue

            # Expandable category row
            if cat_key and item.get("expandable"):
                current_accounts = mapping.get("categories", {}).get(cat_key, []).copy()

                # In edit mode, calculate effective accounts (including pending changes)
                cat_pending_adds = pending_adds.get(cat_key, []) if edit_mode else []
                cat_pending_removes = pending_removes.get(cat_key, []) if edit_mode else []

                # Effective accounts = current - pending_removes + pending_adds
                effective_accounts = [a for a in current_accounts if a not in cat_pending_removes] + cat_pending_adds
                num_accounts = len(effective_accounts)
                num_pending_changes = len(cat_pending_adds) + len(cat_pending_removes)

                # Create row with expand arrow, name, and + button
                row_col1, row_col2, row_col3 = st.columns([0.5, 4, 0.5])

                with row_col1:
                    # Expand/collapse toggle
                    expand_key = f"expand_{cat_key}"
                    if expand_key not in st.session_state:
                        st.session_state[expand_key] = False
                    if st.button("▶" if not st.session_state[expand_key] else "▼", key=f"toggle_{cat_key}"):
                        st.session_state[expand_key] = not st.session_state[expand_key]
                        st.rerun()

                with row_col2:
                    badge = f" ({num_accounts})" if num_accounts > 0 else ""
                    # Show pending indicator in edit mode
                    pending_indicator = f" 🔸" if edit_mode and num_pending_changes > 0 else ""
                    st.markdown(f"{indent}{item['name']}{badge}{pending_indicator}")

                with row_col3:
                    # + button to add accounts
                    if st.button("➕", key=f"add_btn_{cat_key}", help=f"Voeg rekening toe aan {item['name']}"):
                        st.session_state[f"adding_to_{cat_key}"] = True
                        st.rerun()

                # Show assigned accounts when expanded (including pending changes visualization)
                if st.session_state.get(expand_key, False):
                    # First show current accounts (excluding pending removes)
                    for i, acc_code in enumerate(current_accounts):
                        is_pending_remove = acc_code in cat_pending_removes
                        acc = account_lookup.get(acc_code)
                        acc_name = acc["name"][:35] if acc else "Onbekend"
                        acc_col1, acc_col2 = st.columns([4.5, 0.5])
                        with acc_col1:
                            if is_pending_remove:
                                # Show strikethrough for pending removes
                                st.caption(f"{indent}　　~~`{acc_code}` - {acc_name}~~ ❌ _te verwijderen_")
                            else:
                                st.caption(f"{indent}　　`{acc_code}` - {acc_name}")
                        with acc_col2:
                            if is_pending_remove:
                                # Undo remove button
                                if st.button("↩️", key=f"undo_rm_{cat_key}_{i}", help="Ongedaan maken"):
                                    st.session_state.pending_removes[cat_key].remove(acc_code)
                                    if not st.session_state.pending_removes[cat_key]:
                                        del st.session_state.pending_removes[cat_key]
                                    st.rerun()
                            else:
                                if st.button("✕", key=f"rm_{cat_key}_{i}", help="Verwijder"):
                                    if edit_mode:
                                        # In edit mode: add to pending removes
                                        if cat_key not in st.session_state.pending_removes:
                                            st.session_state.pending_removes[cat_key] = []
                                        if acc_code not in st.session_state.pending_removes[cat_key]:
                                            st.session_state.pending_removes[cat_key].append(acc_code)
                                        st.rerun()
                                    else:
                                        # Normal mode: direct remove
                                        current_accounts.remove(acc_code)
                                        mapping["categories"][cat_key] = current_accounts
                                        st.session_state.draggable_mapping = mapping
                                        st.rerun()

                    # Show pending adds (in edit mode)
                    for i, acc_code in enumerate(cat_pending_adds):
                        acc = account_lookup.get(acc_code)
                        acc_name = acc["name"][:35] if acc else "Onbekend"
                        acc_col1, acc_col2 = st.columns([4.5, 0.5])
                        with acc_col1:
                            st.caption(f"{indent}　　`{acc_code}` - {acc_name} ✅ _toe te voegen_")
                        with acc_col2:
                            # Undo add button
                            if st.button("↩️", key=f"undo_add_{cat_key}_{i}", help="Ongedaan maken"):
                                st.session_state.pending_adds[cat_key].remove(acc_code)
                                if not st.session_state.pending_adds[cat_key]:
                                    del st.session_state.pending_adds[cat_key]
                                st.rerun()

                # Show add dialog if active
                if st.session_state.get(f"adding_to_{cat_key}", False):
                    st.markdown(f"**Rekening toevoegen aan {item['name']}:**")
                    options = [f"{acc['code']} - {acc['name'][:40]}" for acc in unassigned_accounts]
                    selected = st.selectbox("Selecteer rekening:", options=[""] + options, key=f"select_{cat_key}")
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("Toevoegen", key=f"confirm_{cat_key}") and selected:
                            code = selected.split(" - ")[0]
                            if edit_mode:
                                # In edit mode: add to pending adds
                                if cat_key not in st.session_state.pending_adds:
                                    st.session_state.pending_adds[cat_key] = []
                                if code not in st.session_state.pending_adds[cat_key]:
                                    st.session_state.pending_adds[cat_key].append(code)
                            else:
                                # Normal mode: direct add
                                current_accounts.append(code)
                                mapping["categories"][cat_key] = current_accounts
                                st.session_state.draggable_mapping = mapping
                            st.session_state[f"adding_to_{cat_key}"] = False
                            st.rerun()
                    with btn_col2:
                        if st.button("Annuleren", key=f"cancel_{cat_key}"):
                            st.session_state[f"adding_to_{cat_key}"] = False
                            st.rerun()

    # -------------------------------------------------------------------------
    # RIGHT COLUMN: Unmapped Accounts with Bulk Selection
    # -------------------------------------------------------------------------
    with col_unmapped:
        st.markdown("### 📋 Niet-toegewezen Rekeningen")
        st.caption(f"{len(unassigned_accounts)} rekeningen beschikbaar")

        # Search box
        search_acc = st.text_input("🔍 Zoek rekening...", key="search_account", placeholder="Code of naam...")

        # Refresh button
        if st.button("🔄 Ververs", key="refresh_accounts"):
            discover_account_groups.clear()
            st.rerun()

        # Sort options
        sort_by = st.selectbox("Sorteren op:", ["Account Number", "Naam", "Saldo"], key="sort_unmapped")

        # Filter and sort accounts
        filtered_accounts = unassigned_accounts
        if search_acc:
            search_lower = search_acc.lower()
            filtered_accounts = [
                acc for acc in unassigned_accounts
                if search_lower in acc["code"].lower() or search_lower in acc["name"].lower()
            ]

        if sort_by == "Naam":
            filtered_accounts = sorted(filtered_accounts, key=lambda x: x["name"])
        elif sort_by == "Saldo":
            filtered_accounts = sorted(filtered_accounts, key=lambda x: abs(x["balance"]), reverse=True)
        else:
            filtered_accounts = sorted(filtered_accounts, key=lambda x: x["code"])

        st.markdown("---")

        # =================================================================
        # BULK SELECTION: Select multiple accounts and assign to category
        # =================================================================
        st.markdown("**Bulk toewijzen:**")

        # Multiselect for accounts
        account_options = [f"{acc['code']} - {acc['name'][:35]}" for acc in filtered_accounts]
        selected_accounts = st.multiselect(
            "Selecteer rekeningen:",
            options=account_options,
            default=[],
            key="bulk_select_accounts",
            placeholder="Klik om rekeningen te selecteren..."
        )

        # Quick select buttons
        sel_col1, sel_col2 = st.columns(2)
        with sel_col1:
            if st.button("Selecteer alle", key="select_all_accounts"):
                st.session_state.bulk_select_accounts = account_options[:100]  # Max 100
                st.rerun()
        with sel_col2:
            if st.button("Wis selectie", key="clear_selection"):
                st.session_state.bulk_select_accounts = []
                st.rerun()

        # Category selector for bulk assignment
        if selected_accounts:
            st.markdown(f"**{len(selected_accounts)} rekening(en) geselecteerd**")

            # Build category options (only non-subtotal categories)
            category_options = []
            for cat_key, cat_info in REPORT_CATEGORIES.items():
                if not cat_info.get("is_subtotal", False):
                    category_options.append((cat_key, cat_info["name"]))

            category_options.sort(key=lambda x: REPORT_CATEGORIES[x[0]].get("order", 99))

            target_category = st.selectbox(
                "Toevoegen aan categorie:",
                options=[c[0] for c in category_options],
                format_func=lambda x: next((c[1] for c in category_options if c[0] == x), x),
                key="bulk_target_category"
            )

            if st.button("➕ Voeg geselecteerde toe", key="bulk_add", type="primary"):
                # Extract account codes from selection
                codes_to_add = [sel.split(" - ")[0] for sel in selected_accounts]

                if edit_mode:
                    # In edit mode: add to pending adds
                    if target_category not in st.session_state.pending_adds:
                        st.session_state.pending_adds[target_category] = []
                    for code in codes_to_add:
                        if code not in st.session_state.pending_adds[target_category]:
                            # Also check it's not already in the mapping
                            existing = mapping.get("categories", {}).get(target_category, [])
                            if code not in existing:
                                st.session_state.pending_adds[target_category].append(code)
                    st.session_state.bulk_select_accounts = []  # Clear selection
                    st.success(f"✅ {len(codes_to_add)} rekening(en) toegevoegd aan pending wijzigingen!")
                    st.rerun()
                else:
                    # Normal mode: direct add
                    if target_category not in mapping["categories"]:
                        mapping["categories"][target_category] = []

                    for code in codes_to_add:
                        if code not in mapping["categories"][target_category]:
                            mapping["categories"][target_category].append(code)

                    st.session_state.draggable_mapping = mapping
                    st.session_state.bulk_select_accounts = []  # Clear selection
                    st.success(f"✅ {len(codes_to_add)} rekening(en) toegevoegd!")
                    st.rerun()

        st.markdown("---")

        # Show remaining unassigned accounts (preview)
        st.markdown("**Niet-geselecteerde rekeningen:**")
        remaining = [acc for acc in filtered_accounts if f"{acc['code']} - {acc['name'][:35]}" not in selected_accounts]
        for acc in remaining[:20]:
            st.caption(f"`{acc['code']}` {acc['name'][:30]}")

        if len(remaining) > 20:
            st.caption(f"... en {len(remaining) - 20} meer")

    # =========================================================================
    # SAVE / RESET BUTTONS
    # =========================================================================
    st.markdown("---")

    # Warning if in edit mode with pending changes
    if edit_mode and total_pending > 0:
        st.warning(f"⚠️ Er zijn {total_pending} pending wijziging(en). Commit of annuleer deze eerst voordat je opslaat of reset.")

    save_col1, save_col2, save_col3 = st.columns([1, 1, 2])

    with save_col1:
        # Disable save in edit mode with pending changes
        save_disabled = edit_mode and total_pending > 0
        if st.button("💾 Opslaan", key="save_mapping", type="primary", disabled=save_disabled):
            success, message = save_draggable_mapping(st.session_state.draggable_mapping)
            if success:
                st.success(f"✅ {message}")
                get_base_year_data.clear()
            else:
                st.error(f"❌ {message}")

    with save_col2:
        # Disable reset in edit mode with pending changes
        reset_disabled = edit_mode and total_pending > 0
        if st.button("🔄 Reset", key="reset_mapping", disabled=reset_disabled):
            st.session_state.draggable_mapping = {
                "categories": {key: [] for key in REPORT_CATEGORIES.keys() if not REPORT_CATEGORIES[key].get("is_subtotal", False)},
                "unassigned": []
            }
            # Also clear edit mode state
            st.session_state.mapping_edit_mode = False
            st.session_state.pending_adds = {}
            st.session_state.pending_removes = {}
            if os.path.exists(MAPPING_STORAGE_FILE):
                os.remove(MAPPING_STORAGE_FILE)
            st.success("Mapping gereset!")
            st.rerun()


def calculate_report_with_mapping(company_id, year, mapping=None):
    """
    Calculate the financial report using the draggable mapping configuration.

    Args:
        company_id: Company ID to calculate for
        year: Year to calculate
        mapping: Optional mapping dict, uses saved mapping if not provided

    Returns:
        Dict with calculated values for each category
    """
    if mapping is None:
        mapping = get_draggable_mapping()

    categories = mapping.get("categories", {})
    results = {}

    # First pass: calculate non-subtotal categories from account data
    for cat_key, cat_info in REPORT_CATEGORIES.items():
        if cat_info.get("is_subtotal", False):
            continue

        account_codes = categories.get(cat_key, [])
        if not account_codes:
            results[cat_key] = 0
            continue

        # Fetch data for these accounts
        try:
            start_date = f"{year}-01-01"
            end_date = f"{year}-12-31"

            total = 0
            for code in account_codes:
                domain = [
                    ["date", ">=", start_date],
                    ["date", "<=", end_date],
                    ["parent_state", "=", "posted"],
                    ["account_id.code", "=like", f"{code}%"]
                ]
                if company_id:
                    domain.append(["company_id", "=", company_id])

                data = odoo_read_group(
                    "account.move.line",
                    domain,
                    ["balance:sum"],
                    []
                )

                if data and len(data) > 0:
                    balance = data[0].get("balance:sum", 0)
                    # Apply sign flip if configured
                    if cat_info.get("sign_flip", False):
                        balance = -balance
                    total += balance

            results[cat_key] = total
        except Exception as e:
            print(f"Error calculating {cat_key}: {e}")
            results[cat_key] = 0

    # Second pass: calculate subtotals
    for cat_key, cat_info in REPORT_CATEGORIES.items():
        if not cat_info.get("is_subtotal", False):
            continue

        calculation = cat_info.get("calculation", "")
        if not calculation:
            results[cat_key] = 0
            continue

        # Parse and evaluate the calculation
        try:
            # Replace category names with their values
            expr = calculation
            for key in results.keys():
                expr = expr.replace(key, str(results.get(key, 0)))

            # Safely evaluate the expression
            # Only allow basic math operations
            allowed_chars = set("0123456789.+-*/()")
            clean_expr = "".join(c for c in expr if c in allowed_chars or c == " ")
            results[cat_key] = eval(clean_expr)
        except Exception as e:
            print(f"Error calculating subtotal {cat_key}: {e}")
            results[cat_key] = 0

    return results


@st.cache_data(ttl=3600, show_spinner=False)
def get_base_year_data(company_id, base_year, revenue_patterns=None, cogs_patterns=None, expense_categories=None):
    """
    Fetch annual financial data from Odoo for a specific year to use as forecast base.

    Args:
        company_id: Company ID to filter by (None for all companies)
        base_year: Year to fetch data from (e.g., 2024, 2025)
        revenue_patterns: List of account prefixes for revenue (default: ["70", "71", "72", "73", "74"])
        cogs_patterns: List of account prefixes for COGS (default: ["60"])
        expense_categories: Dict of category code -> name for expenses (default: EXPENSE_CATEGORIES)

    Returns:
        Dict with aggregated annual data:
        - average_monthly_revenue: Average monthly revenue
        - average_monthly_cogs: Average monthly COGS
        - average_monthly_expenses: Dict of average monthly expenses per category
        - total_revenue: Total annual revenue
        - total_cogs: Total annual COGS
        - months_with_data: Number of months with actual data
    """
    # Use defaults if not provided
    if revenue_patterns is None:
        revenue_patterns = DEFAULT_ACCOUNT_MAPPING["revenue"]["account_patterns"]
    if cogs_patterns is None:
        cogs_patterns = DEFAULT_ACCOUNT_MAPPING["cogs"]["account_patterns"]
    if expense_categories is None:
        expense_categories = EXPENSE_CATEGORIES

    try:
        start_date = f"{base_year}-01-01"
        end_date = f"{base_year}-12-31"

        # Build domain filters
        base_domain = [
            ["date", ">=", start_date],
            ["date", "<=", end_date],
            ["parent_state", "=", "posted"]
        ]

        if company_id:
            base_domain.append(["company_id", "=", company_id])

        # Fetch revenue from multiple account patterns
        revenue_data = []
        for pattern in revenue_patterns:
            revenue_domain = base_domain + [["account_id.code", "=like", f"{pattern}%"]]
            data = odoo_read_group(
                "account.move.line",
                revenue_domain,
                ["balance:sum"],
                ["date:month"]
            )
            revenue_data.extend(data)

        # Fetch COGS from multiple account patterns
        cogs_data = []
        for pattern in cogs_patterns:
            cogs_domain = base_domain + [["account_id.code", "=like", f"{pattern}%"]]
            data = odoo_read_group(
                "account.move.line",
                cogs_domain,
                ["balance:sum"],
                ["date:month"]
            )
            cogs_data.extend(data)

        # Fetch operating expenses per category
        expenses_by_category = {}
        for cat_code in expense_categories.keys():
            exp_domain = base_domain + [["account_id.code", "=like", f"{cat_code}%"]]
            exp_data = odoo_read_group(
                "account.move.line",
                exp_domain,
                ["balance:sum"],
                ["date:month"]
            )
            expenses_by_category[cat_code] = exp_data

        # Calculate totals and averages
        # Revenue: typically negative in Odoo (credit), so we flip the sign
        total_revenue = sum(-item.get("balance:sum", 0) for item in revenue_data)
        total_cogs = sum(item.get("balance:sum", 0) for item in cogs_data)

        # Count months with revenue data to calculate proper averages
        months_with_data = len([r for r in revenue_data if r.get("balance:sum", 0) != 0])
        if months_with_data == 0:
            months_with_data = 1  # Avoid division by zero

        average_monthly_revenue = total_revenue / months_with_data
        average_monthly_cogs = total_cogs / months_with_data

        # Calculate average expenses per category
        average_monthly_expenses = {}
        for cat_code, cat_data in expenses_by_category.items():
            total_cat = sum(item.get("balance:sum", 0) for item in cat_data)
            average_monthly_expenses[cat_code] = total_cat / months_with_data

        return {
            "base_year": base_year,
            "average_monthly_revenue": average_monthly_revenue,
            "average_monthly_cogs": average_monthly_cogs,
            "average_monthly_expenses": average_monthly_expenses,
            "total_revenue": total_revenue,
            "total_cogs": total_cogs,
            "months_with_data": months_with_data,
            "cogs_percentage": (total_cogs / total_revenue) if total_revenue > 0 else 0.6
        }
    except Exception as e:
        # Note: st.error() cannot be used inside cached functions
        # Error will be handled by caller showing "Geen data gevonden"
        print(f"Error fetching base year data: {e}")
        return None

def export_forecast_to_csv(forecast, calculated):
    """Export forecast data to CSV format"""
    periods = forecast.get("periods", [])

    rows = []
    # Header
    header = ["Categorie"] + [p["label"] for p in periods] + ["Totaal"]
    rows.append(header)

    # Revenue
    revenue_row = ["Omzet"] + [f"{v:,.0f}" for v in calculated["revenue"]] + [f"{calculated['total_revenue']:,.0f}"]
    rows.append(revenue_row)

    # COGS
    cogs_row = ["Kostprijs Verkopen"] + [f"{v:,.0f}" for v in calculated["cogs"]] + [f"{sum(calculated['cogs']):,.0f}"]
    rows.append(cogs_row)

    # Gross Profit
    gp_row = ["Brutowinst"] + [f"{v:,.0f}" for v in calculated["gross_profit"]] + [f"{calculated['total_gross_profit']:,.0f}"]
    rows.append(gp_row)

    # Operating Expenses by category
    for code, cat_data in forecast["operating_expenses"].items():
        exp_row = [cat_data["name"]] + [f"{v:,.0f}" for v in cat_data["values"]] + [f"{sum(cat_data['values']):,.0f}"]
        rows.append(exp_row)

    # Totals
    opex_row = ["Totaal Operationele Kosten"] + [f"{v:,.0f}" for v in calculated["operating_expenses"]] + [f"{sum(calculated['operating_expenses']):,.0f}"]
    rows.append(opex_row)

    ebit_row = ["EBIT"] + [f"{v:,.0f}" for v in calculated["ebit"]] + [f"{sum(calculated['ebit']):,.0f}"]
    rows.append(ebit_row)

    ebitda_row = ["EBITDA"] + [f"{v:,.0f}" for v in calculated["ebitda"]] + [f"{calculated['total_ebitda']:,.0f}"]
    rows.append(ebitda_row)

    ni_row = ["Netto Resultaat"] + [f"{v:,.0f}" for v in calculated["net_income"]] + [f"{calculated['total_net_income']:,.0f}"]
    rows.append(ni_row)

    # Convert to CSV string
    csv_content = "\n".join([";".join(row) for row in rows])
    return csv_content

def export_forecast_to_excel(forecast, calculated):
    """Export forecast data to Excel format (as bytes)"""
    try:
        import io

        periods = forecast.get("periods", [])
        period_labels = [p["label"] for p in periods]

        # Build dataframe
        data = {
            "Categorie": [],
        }
        for label in period_labels:
            data[label] = []
        data["Totaal"] = []

        # Add rows
        def add_row(name, values, total):
            data["Categorie"].append(name)
            for i, label in enumerate(period_labels):
                data[label].append(values[i] if i < len(values) else 0)
            data["Totaal"].append(total)

        add_row("Omzet", calculated["revenue"], calculated["total_revenue"])
        add_row("Kostprijs Verkopen", calculated["cogs"], sum(calculated["cogs"]))
        add_row("Brutowinst", calculated["gross_profit"], calculated["total_gross_profit"])

        for code, cat_data in forecast["operating_expenses"].items():
            add_row(cat_data["name"], cat_data["values"], sum(cat_data["values"]))

        add_row("Totaal Operationele Kosten", calculated["operating_expenses"], sum(calculated["operating_expenses"]))
        add_row("EBIT", calculated["ebit"], sum(calculated["ebit"]))
        add_row("EBITDA", calculated["ebitda"], calculated["total_ebitda"])
        add_row("Netto Resultaat", calculated["net_income"], calculated["total_net_income"])

        df = pd.DataFrame(data)

        # Export to Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Forecast', index=False)

        return output.getvalue()
    except Exception as e:
        st.error(f"Excel export fout: {e}")
        return None

def validate_forecast(forecast):
    """
    Validate forecast data for completeness and reasonableness.

    Returns:
        Tuple of (is_valid: bool, warnings: list, errors: list)
    """
    warnings = []
    errors = []

    # Check for name
    if not forecast.get("name"):
        errors.append("Forecast naam is verplicht")

    # Check revenue
    revenue = forecast.get("revenue", {}).get("values", [])
    if all(v == 0 for v in revenue):
        warnings.append("Alle omzetwaarden zijn 0 - is dit correct?")

    # Check for unrealistic growth rates
    assumptions = forecast.get("assumptions", {})
    if assumptions.get("customer_acquisition_rate", 0) > 0.50:
        warnings.append("Klantacquisitie rate >50% is onrealistisch hoog")

    if assumptions.get("churn_rate", 0) > 0.30:
        warnings.append("Churn rate >30% is onrealistisch hoog")

    # Check COGS percentage
    cogs = forecast.get("cogs", {})
    if cogs.get("input_type") == "percentage":
        pct = cogs.get("percentage_of_revenue", 0)
        if pct > 0.95:
            warnings.append("Kostprijs >95% van omzet laat zeer weinig brutomarge")
        elif pct < 0.10:
            warnings.append("Kostprijs <10% van omzet is ongebruikelijk laag")

    # Check expense totals vs revenue
    revenue_total = sum(revenue)
    expense_total = 0
    for cat_data in forecast.get("operating_expenses", {}).values():
        expense_total += sum(cat_data.get("values", []))

    if revenue_total > 0 and expense_total / revenue_total > 0.80:
        warnings.append("Operationele kosten >80% van omzet - controleer winstgevendheid")

    is_valid = len(errors) == 0
    return is_valid, warnings, errors

# =============================================================================
# MAIN APP
# =============================================================================

def main():
    st.title("📊 LAB Groep Financial Dashboard")
    st.caption("Real-time data uit Odoo | v18 - Directors Mode")
    
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
    
    # Directors Mode Login
    if get_directors_password():
        st.sidebar.markdown("### 🔐 Directors Mode")
        if not is_directors_mode_active():
            with st.sidebar.expander("Directors Login", expanded=False):
                pwd = st.text_input("Wachtwoord", type="password", key="dir_pwd")
                if st.button("Inloggen", key="dir_login"):
                    valid, err = verify_directors_password(pwd)
                    if valid:
                        st.session_state.directors_authenticated = True
                        st.rerun()
                    else:
                        st.error("Ongeldig wachtwoord")
        else:
            st.sidebar.success("✅ Directors Mode")
            if st.sidebar.button("Uitloggen", key="dir_logout"):
                st.session_state.directors_authenticated = False
                st.rerun()
        st.sidebar.markdown("---")
    
    # Entiteit selectie (dynamisch)
    active_companies = get_active_companies()
    entity_options = ["Alle bedrijven"] + list(active_companies.values())
    selected_entity = st.sidebar.selectbox("🏢 Entiteit", entity_options)
    
    company_id = None
    is_extended = False
    instance_key = None
    if selected_entity != "Alle bedrijven":
        company_id = [k for k, v in active_companies.items() if v == selected_entity][0]
        instance_key, _ = get_instance_for_company(company_id)
        is_extended = instance_key is not None
    
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
    tabs = st.tabs(["💳 Overzicht", "🏦 Bank", "📄 Facturen", "🏆 Producten", "🗺️ Klantenkaart", "📉 Kosten", "📈 Cashflow", "📊 Balans", "💬 AI Chat", "📋 Maandafsluiting", "🔮 Forecast", "🎯 Budget 2026"])
    
    # =========================================================================
    # TAB 1: OVERZICHT
    # =========================================================================
    with tabs[0]:
        # Extended entity handler
        if is_extended and instance_key:
            st.subheader(f"📊 {selected_entity}")
            with st.spinner("Data laden..."):
                # Revenue
                rev = odoo_call_extended(instance_key, "account.move.line", "search_read",
                    [("date", ">=", f"{selected_year}-01-01"), ("date", "<=", f"{selected_year}-12-31"),
                     ("account_id.code", "=like", "8%"), ("parent_state", "=", "posted")],
                    ["balance", "date"])
                revenue = -sum(r.get("balance", 0) for r in rev) if rev else 0
                
                # Costs
                costs_4 = odoo_call_extended(instance_key, "account.move.line", "search_read",
                    [("date", ">=", f"{selected_year}-01-01"), ("date", "<=", f"{selected_year}-12-31"),
                     ("account_id.code", "=like", "4%"), ("parent_state", "=", "posted")],
                    ["balance"])
                costs_7 = odoo_call_extended(instance_key, "account.move.line", "search_read",
                    [("date", ">=", f"{selected_year}-01-01"), ("date", "<=", f"{selected_year}-12-31"),
                     ("account_id.code", "=like", "7%"), ("parent_state", "=", "posted")],
                    ["balance"])
                costs = sum(c.get("balance", 0) for c in (costs_4 or [])) + sum(c.get("balance", 0) for c in (costs_7 or []))
                
                result = revenue - costs
                
                c1, c2, c3 = st.columns(3)
                c1.metric("💰 Omzet", f"€{revenue:,.0f}")
                c2.metric("📉 Kosten", f"€{costs:,.0f}")
                c3.metric("📊 Resultaat", f"€{result:,.0f}")
                
                # Monthly chart
                if rev:
                    import pandas as pd
                    df = pd.DataFrame(rev)
                    df["date"] = pd.to_datetime(df["date"])
                    df["month"] = df["date"].dt.month
                    df["omzet"] = -df["balance"]
                    monthly = df.groupby("month")["omzet"].sum().reset_index()
                    months = {1:"Jan",2:"Feb",3:"Mrt",4:"Apr",5:"Mei",6:"Jun",7:"Jul",8:"Aug",9:"Sep",10:"Okt",11:"Nov",12:"Dec"}
                    monthly["maand"] = monthly["month"].map(months)
                    fig = px.bar(monthly, x="maand", y="omzet", title=f"Maandelijkse Omzet {selected_year}")
                    st.plotly_chart(fig, use_container_width=True)
            st.stop()
        
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
        monthly = {}  # Initialize outside if-block to prevent UnboundLocalError
        if revenue_agg:
            
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
            
        # Create df_monthly from monthly data (works even if monthly is empty)
        if monthly:
            df_monthly = pd.DataFrame([
                {"Maand": k, "Omzet": v["omzet"], "Kosten": v["kosten"]}
                for k, v in sorted(monthly.items())
            ])
        else:
            df_monthly = pd.DataFrame(columns=["Maand", "Omzet", "Kosten"])
        
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

        # =====================================================================
        # OMZET WEEK-OP-WEEK: JAARVERGELIJKING
        # =====================================================================
        st.markdown("---")
        st.subheader("📅 Omzet Week-op-Week: Vergelijking met Vorig Jaar" + (" (excl. IC)" if exclude_intercompany else ""))

        prev_year = selected_year - 1
        with st.spinner(f"Weekdata {selected_year} en {prev_year} laden..."):
            weekly_current = get_weekly_revenue(selected_year, company_id, exclude_intercompany)
            weekly_prev = get_weekly_revenue(prev_year, company_id, exclude_intercompany)

        if weekly_current or weekly_prev:
            # Bouw DataFrames geïndexeerd op weeknummer
            df_cur = pd.DataFrame(weekly_current) if weekly_current else pd.DataFrame(columns=["week_num", "omzet"])
            df_prev = pd.DataFrame(weekly_prev) if weekly_prev else pd.DataFrame(columns=["week_num", "omzet"])

            # Aggregeer per weeknummer (voor het geval er duplicaten zijn)
            if not df_cur.empty:
                df_cur = df_cur.groupby("week_num", as_index=False)["omzet"].sum()
            if not df_prev.empty:
                df_prev = df_prev.groupby("week_num", as_index=False)["omzet"].sum()

            # Maak een volledig weeknummer bereik (1-53)
            all_weeks = sorted(set(
                list(df_cur["week_num"].unique() if not df_cur.empty else []) +
                list(df_prev["week_num"].unique() if not df_prev.empty else [])
            ))

            # Merge op weeknummer
            df_yoy = pd.DataFrame({"Week": all_weeks})
            if not df_cur.empty:
                df_yoy = df_yoy.merge(
                    df_cur.rename(columns={"omzet": f"Omzet {selected_year}"}),
                    left_on="Week", right_on="week_num", how="left"
                ).drop(columns=["week_num"], errors="ignore")
            else:
                df_yoy[f"Omzet {selected_year}"] = 0

            if not df_prev.empty:
                df_yoy = df_yoy.merge(
                    df_prev.rename(columns={"omzet": f"Omzet {prev_year}"}),
                    left_on="Week", right_on="week_num", how="left"
                ).drop(columns=["week_num"], errors="ignore")
            else:
                df_yoy[f"Omzet {prev_year}"] = 0

            df_yoy = df_yoy.fillna(0)

            fig_yoy = go.Figure()

            # Vorig jaar als lichtere achtergrond
            fig_yoy.add_trace(go.Bar(
                x=df_yoy["Week"],
                y=df_yoy[f"Omzet {prev_year}"],
                name=str(prev_year),
                marker_color="#87CEEB",
                opacity=0.6,
                hovertemplate=f"<b>Week %{{x}}</b><br>{prev_year}: €%{{y:,.0f}}<extra></extra>"
            ))

            # Huidig jaar als donkere balk
            fig_yoy.add_trace(go.Bar(
                x=df_yoy["Week"],
                y=df_yoy[f"Omzet {selected_year}"],
                name=str(selected_year),
                marker_color="#1e3a5f",
                hovertemplate=f"<b>Week %{{x}}</b><br>{selected_year}: €%{{y:,.0f}}<extra></extra>"
            ))

            fig_yoy.update_layout(
                barmode="group",
                height=450,
                xaxis=dict(
                    title="Weeknummer",
                    dtick=2,
                    tickformat="d"
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
                plot_bgcolor="white"
            )

            st.plotly_chart(fig_yoy, use_container_width=True)

            # YoY statistieken
            total_cur = df_yoy[f"Omzet {selected_year}"].sum()
            total_prev = df_yoy[f"Omzet {prev_year}"].sum()
            yoy_change = ((total_cur - total_prev) / total_prev * 100) if total_prev > 0 else 0

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(f"Totaal {selected_year}", f"€{total_cur:,.0f}")
            with col2:
                st.metric(f"Totaal {prev_year}", f"€{total_prev:,.0f}")
            with col3:
                st.metric("Verschil YoY", f"{yoy_change:+.1f}%",
                         delta=f"€{total_cur - total_prev:+,.0f}")
        else:
            st.info("Geen weekdata beschikbaar voor de jaarvergelijking")

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
        prod_subtabs = st.tabs(["📦 Productcategorieën", "🏅 Top Producten", "🎨 Verf vs Behang", "📊 Categorie Trend"])
        
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

        # Subtab 4: Categorie Trend (WoW + Cumulatief + YoY)
        with prod_subtabs[3]:
            st.subheader(f"📊 Omzet per Categorie - Week Trend {selected_year}")

            # Helper: haal gecombineerde productverkopen op (POS + facturen)
            def _fetch_combined_product_sales(year, cid):
                """Haal alle productverkopen op, POS + facturen gecombineerd."""
                all_sales = []
                # POS data (Conceptstore = company 1)
                if cid == 1 or cid is None:
                    pos_data = get_pos_product_sales_with_dates(year, 1 if cid is None else cid)
                    # Normaliseer POS data: qty -> quantity voor uniforme verwerking
                    for p in pos_data:
                        all_sales.append({
                            "product_id": p.get("product_id"),
                            "price_subtotal": p.get("price_subtotal", 0),
                            "quantity": p.get("qty", 0),
                            "date": p.get("date", ""),
                        })
                # Factuurdata (Shops, Projects, of alle)
                if cid != 1:
                    inv_data = get_product_sales_with_dates(year, cid)
                    for p in inv_data:
                        all_sales.append({
                            "product_id": p.get("product_id"),
                            "price_subtotal": p.get("price_subtotal", 0),
                            "quantity": p.get("quantity", 0),
                            "date": p.get("date", ""),
                        })
                return all_sales

            # Helper: groepeer sales per week voor een categorie
            def _group_by_week(sales_data, cat_lookup, category_name):
                """Groepeer verkoopdata per week voor een specifieke categorie."""
                from datetime import datetime as dt_cls
                weekly = {}
                for p in sales_data:
                    prod = p.get("product_id")
                    if not prod:
                        continue
                    cat = cat_lookup.get(prod[0], [None, "Onbekend"])
                    if (cat[1] if cat else "Onbekend") != category_name:
                        continue
                    date_str = p.get("date", "")
                    if not date_str:
                        continue
                    try:
                        d = dt_cls.strptime(date_str[:10], "%Y-%m-%d")
                        iso_cal = d.isocalendar()
                        week_num = iso_cal[1]
                        week_start = dt_cls.strptime(f"{iso_cal[0]}-W{week_num:02d}-1", "%G-W%V-%u")
                        week_key = week_start.strftime("%Y-%m-%d")
                    except (ValueError, IndexError):
                        continue
                    if week_key not in weekly:
                        weekly[week_key] = {"week_num": week_num, "omzet": 0, "aantal": 0}
                    weekly[week_key]["omzet"] += p.get("price_subtotal", 0)
                    weekly[week_key]["aantal"] += p.get("quantity", 0)
                return weekly

            with st.spinner("Productdata laden..."):
                cat_trend_sales = _fetch_combined_product_sales(selected_year, company_id)

            if cat_trend_sales:
                # Verzamel product IDs en haal categorieën op
                cat_trend_product_ids = tuple(set(
                    p.get("product_id", [None])[0] for p in cat_trend_sales if p.get("product_id")
                ))
                cat_trend_cats = {}
                if cat_trend_product_ids:
                    cat_trend_cats = get_product_categories_for_ids(cat_trend_product_ids)

                # Bouw lijst van unieke categorieën gesorteerd op omzet
                cat_totals = {}
                for p in cat_trend_sales:
                    prod = p.get("product_id")
                    if prod:
                        cat = cat_trend_cats.get(prod[0], [None, "Onbekend"])
                        cat_name = cat[1] if cat else "Onbekend"
                        cat_totals[cat_name] = cat_totals.get(cat_name, 0) + p.get("price_subtotal", 0)

                category_names = [k for k, v in sorted(cat_totals.items(), key=lambda x: -x[1]) if v != 0]

                if category_names:
                    selected_category = st.selectbox(
                        "Selecteer productcategorie",
                        category_names,
                        key="cat_trend_filter"
                    )

                    # Groepeer huidig jaar per week
                    weekly_cat = _group_by_week(cat_trend_sales, cat_trend_cats, selected_category)

                    # Haal ook vorig jaar op voor YoY vergelijking
                    prev_year = selected_year - 1
                    with st.spinner(f"Data {prev_year} laden voor vergelijking..."):
                        cat_trend_sales_prev = _fetch_combined_product_sales(prev_year, company_id)

                    # Categorieën vorig jaar ophalen (kan andere producten bevatten)
                    cat_trend_cats_prev = cat_trend_cats.copy()
                    if cat_trend_sales_prev:
                        prev_product_ids = tuple(set(
                            p.get("product_id", [None])[0] for p in cat_trend_sales_prev if p.get("product_id")
                        ))
                        new_ids = tuple(pid for pid in prev_product_ids if pid not in cat_trend_cats_prev)
                        if new_ids:
                            extra_cats = get_product_categories_for_ids(new_ids)
                            cat_trend_cats_prev.update(extra_cats)

                    weekly_cat_prev = _group_by_week(cat_trend_sales_prev, cat_trend_cats_prev, selected_category) if cat_trend_sales_prev else {}

                    if weekly_cat or weekly_cat_prev:
                        df_cur = pd.DataFrame([
                            {"week_num": v["week_num"], "omzet": v["omzet"], "aantal": v["aantal"]}
                            for k, v in sorted(weekly_cat.items())
                        ]) if weekly_cat else pd.DataFrame(columns=["week_num", "omzet", "aantal"])

                        df_prev = pd.DataFrame([
                            {"week_num": v["week_num"], "omzet": v["omzet"], "aantal": v["aantal"]}
                            for k, v in sorted(weekly_cat_prev.items())
                        ]) if weekly_cat_prev else pd.DataFrame(columns=["week_num", "omzet", "aantal"])

                        # Aggregeer per weeknummer
                        if not df_cur.empty:
                            df_cur = df_cur.groupby("week_num", as_index=False)["omzet"].sum()
                        if not df_prev.empty:
                            df_prev = df_prev.groupby("week_num", as_index=False)["omzet"].sum()

                        # Merge beide jaren op weeknummer
                        all_weeks = sorted(set(
                            list(df_cur["week_num"].unique() if not df_cur.empty else []) +
                            list(df_prev["week_num"].unique() if not df_prev.empty else [])
                        ))
                        df_merged = pd.DataFrame({"Week": all_weeks})

                        if not df_cur.empty:
                            df_merged = df_merged.merge(
                                df_cur.rename(columns={"omzet": f"Omzet {selected_year}"}),
                                left_on="Week", right_on="week_num", how="left"
                            ).drop(columns=["week_num"], errors="ignore")
                        else:
                            df_merged[f"Omzet {selected_year}"] = 0

                        if not df_prev.empty:
                            df_merged = df_merged.merge(
                                df_prev.rename(columns={"omzet": f"Omzet {prev_year}"}),
                                left_on="Week", right_on="week_num", how="left"
                            ).drop(columns=["week_num"], errors="ignore")
                        else:
                            df_merged[f"Omzet {prev_year}"] = 0

                        df_merged = df_merged.fillna(0)

                        # Cumulatief per jaar
                        df_merged[f"Cumulatief {selected_year}"] = df_merged[f"Omzet {selected_year}"].cumsum()
                        df_merged[f"Cumulatief {prev_year}"] = df_merged[f"Omzet {prev_year}"].cumsum()

                        # ---- Grafiek 1: Week-op-Week vergelijking ----
                        st.markdown(f"#### Week-op-Week: {selected_year} vs {prev_year}")

                        fig_wow = go.Figure()

                        fig_wow.add_trace(go.Bar(
                            x=df_merged["Week"],
                            y=df_merged[f"Omzet {prev_year}"],
                            name=str(prev_year),
                            marker_color="#87CEEB",
                            opacity=0.6,
                            hovertemplate=f"<b>Week %{{x}}</b><br>{prev_year}: €%{{y:,.0f}}<extra></extra>"
                        ))

                        fig_wow.add_trace(go.Bar(
                            x=df_merged["Week"],
                            y=df_merged[f"Omzet {selected_year}"],
                            name=str(selected_year),
                            marker_color="#1e3a5f",
                            hovertemplate=f"<b>Week %{{x}}</b><br>{selected_year}: €%{{y:,.0f}}<extra></extra>"
                        ))

                        fig_wow.update_layout(
                            barmode="group",
                            height=450,
                            xaxis=dict(title="Weeknummer", dtick=2, tickformat="d"),
                            yaxis=dict(title="Omzet (€)", tickformat=",.0f", gridcolor="#e0e0e0"),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                            hovermode="x unified",
                            plot_bgcolor="white"
                        )

                        st.plotly_chart(fig_wow, use_container_width=True)

                        # ---- Grafiek 2: Cumulatieve vergelijking ----
                        st.markdown(f"#### Cumulatief: {selected_year} vs {prev_year}")

                        fig_cum = go.Figure()

                        fig_cum.add_trace(go.Scatter(
                            x=df_merged["Week"],
                            y=df_merged[f"Cumulatief {prev_year}"],
                            name=str(prev_year),
                            line=dict(color="#87CEEB", width=2, dash="dash"),
                            hovertemplate=f"<b>Week %{{x}}</b><br>{prev_year}: €%{{y:,.0f}}<extra></extra>"
                        ))

                        fig_cum.add_trace(go.Scatter(
                            x=df_merged["Week"],
                            y=df_merged[f"Cumulatief {selected_year}"],
                            name=str(selected_year),
                            fill="tonexty",
                            line=dict(color="#1e3a5f", width=2),
                            fillcolor="rgba(30, 58, 95, 0.10)",
                            hovertemplate=f"<b>Week %{{x}}</b><br>{selected_year}: €%{{y:,.0f}}<extra></extra>"
                        ))

                        fig_cum.update_layout(
                            height=450,
                            xaxis=dict(title="Weeknummer", dtick=2, tickformat="d"),
                            yaxis=dict(title="Cumulatieve Omzet (€)", tickformat=",.0f", gridcolor="#e0e0e0"),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                            hovermode="x unified",
                            plot_bgcolor="white"
                        )

                        st.plotly_chart(fig_cum, use_container_width=True)

                        # ---- YoY Statistieken ----
                        st.markdown("---")
                        total_cur_cat = df_merged[f"Omzet {selected_year}"].sum()
                        total_prev_cat = df_merged[f"Omzet {prev_year}"].sum()
                        yoy_cat_change = ((total_cur_cat - total_prev_cat) / total_prev_cat * 100) if total_prev_cat > 0 else 0
                        avg_cur = df_merged.loc[df_merged[f"Omzet {selected_year}"] > 0, f"Omzet {selected_year}"].mean() if not df_merged.empty else 0
                        avg_prev = df_merged.loc[df_merged[f"Omzet {prev_year}"] > 0, f"Omzet {prev_year}"].mean() if not df_merged.empty else 0

                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric(f"Totaal {selected_year}", f"€{total_cur_cat:,.0f}")
                        with col2:
                            st.metric(f"Totaal {prev_year}", f"€{total_prev_cat:,.0f}")
                        with col3:
                            st.metric("Verschil YoY", f"{yoy_cat_change:+.1f}%",
                                     delta=f"€{total_cur_cat - total_prev_cat:+,.0f}")
                        with col4:
                            st.metric("Gem./week", f"€{avg_cur:,.0f}",
                                     delta=f"€{avg_cur - avg_prev:+,.0f} vs {prev_year}")
                    else:
                        st.info(f"Geen weekdata beschikbaar voor categorie '{selected_category}'")
                else:
                    st.info("Geen productcategorieën gevonden")
            else:
                st.info("Geen productverkopen gevonden voor deze selectie")

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

        # =====================================================================
        # MODUS SELECTIE: PROGNOSE OF HISTORISCH
        # =====================================================================
        mode_col1, mode_col2 = st.columns([1, 3])
        with mode_col1:
            cashflow_mode = st.radio(
                "Modus",
                options=["Prognose", "Historisch"],
                key="cf_mode",
                horizontal=True,
                help="Prognose: huidige situatie + toekomst voorspelling. Historisch: bekijk cashflow van een vorig jaar."
            )
        with mode_col2:
            if cashflow_mode == "Historisch":
                cf_historical_year = st.selectbox(
                    "Jaar",
                    options=list(range(datetime.now().year, 2019, -1)),
                    key="cf_historical_year"
                )

        # =====================================================================
        # HISTORISCHE MODUS
        # =====================================================================
        if cashflow_mode == "Historisch":
            st.info(f"📜 Historische cashflow analyse voor **{entity_label}** - Jaar **{cf_historical_year}**")

            # Haal historische data op voor het geselecteerde jaar
            cf_hist_company_id = company_id if selected_entity != "Alle bedrijven" else None
            historical_year_data = get_historical_bank_data_by_year(cf_historical_year, cf_hist_company_id)

            if historical_year_data:
                # Sorteer per week
                sorted_weeks = sorted(historical_year_data.keys())

                # Bereken cumulatief saldo
                cumulative_balance = 0
                all_hist_data = []
                for week_key in sorted_weeks:
                    week_data = historical_year_data[week_key]
                    cumulative_balance += week_data["net"]
                    week_num = datetime.strptime(week_key, "%Y-%m-%d").isocalendar()[1]
                    all_hist_data.append({
                        "week_key": week_key,
                        "week_label": f"Week {week_num}",
                        "week_start": week_data["week_start"],
                        "inflow": week_data["inflow"],
                        "outflow": week_data["outflow"],
                        "net": week_data["net"],
                        "balance": cumulative_balance
                    })

                df_hist_year = pd.DataFrame(all_hist_data)

                # Metrics voor het jaar
                total_inflow = df_hist_year["inflow"].sum()
                total_outflow = df_hist_year["outflow"].sum()
                total_net = total_inflow - total_outflow
                avg_weekly_inflow = total_inflow / len(df_hist_year)
                avg_weekly_outflow = total_outflow / len(df_hist_year)

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("📥 Totaal Ontvangen", f"€{total_inflow:,.0f}")
                with col2:
                    st.metric("📤 Totaal Uitgegeven", f"€{total_outflow:,.0f}")
                with col3:
                    st.metric("💰 Netto Cashflow", f"€{total_net:,.0f}")
                with col4:
                    st.metric("📊 Gem. Wekelijks", f"€{avg_weekly_inflow - avg_weekly_outflow:,.0f}")

                st.markdown("---")

                # Grafiek met range slider
                fig_hist = go.Figure()

                fig_hist.add_trace(go.Scatter(
                    x=df_hist_year["week_label"],
                    y=df_hist_year["balance"],
                    mode="lines+markers",
                    name="Cumulatief Saldo",
                    line=dict(color="#2E7D32", width=3),
                    marker=dict(size=6),
                    hovertemplate="<b>%{x}</b><br>Saldo: €%{y:,.0f}<extra></extra>"
                ))

                fig_hist.add_trace(go.Bar(
                    x=df_hist_year["week_label"],
                    y=df_hist_year["inflow"],
                    name="Ontvangsten",
                    marker_color="rgba(76, 175, 80, 0.5)",
                    hovertemplate="<b>%{x}</b><br>Ontvangsten: €%{y:,.0f}<extra></extra>"
                ))

                fig_hist.add_trace(go.Bar(
                    x=df_hist_year["week_label"],
                    y=[-x for x in df_hist_year["outflow"]],
                    name="Uitgaven",
                    marker_color="rgba(244, 67, 54, 0.5)",
                    hovertemplate="<b>%{x}</b><br>Uitgaven: €%{y:,.0f}<extra></extra>"
                ))

                fig_hist.add_hline(y=0, line_dash="dash", line_color="red", line_width=1)

                fig_hist.update_layout(
                    height=500,
                    title=f"📈 Historische Cashflow {cf_historical_year}",
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
                    ),
                    xaxis=dict(
                        rangeslider=dict(visible=True),
                        type="category"
                    )
                )

                st.plotly_chart(fig_hist, use_container_width=True)

                # Detail tabel
                with st.expander("📊 Details per week", expanded=False):
                    df_display = df_hist_year.copy()
                    df_display["week_start"] = pd.to_datetime(df_display["week_start"]).dt.strftime("%d-%m-%Y")
                    st.dataframe(
                        df_display[["week_label", "week_start", "inflow", "outflow", "net", "balance"]].rename(
                            columns={
                                "week_label": "Week",
                                "week_start": "Week Start",
                                "inflow": "Ontvangsten",
                                "outflow": "Uitgaven",
                                "net": "Netto",
                                "balance": "Cumulatief"
                            }
                        ).style.format({
                            "Ontvangsten": "€{:,.0f}",
                            "Uitgaven": "€{:,.0f}",
                            "Netto": "€{:,.0f}",
                            "Cumulatief": "€{:,.0f}"
                        }),
                        use_container_width=True,
                        hide_index=True
                    )

                # Download optie
                csv_data = df_hist_year.to_csv(index=False)
                st.download_button(
                    label="📥 Download CSV",
                    data=csv_data,
                    file_name=f"cashflow_{cf_historical_year}.csv",
                    mime="text/csv"
                )
            else:
                st.warning(f"Geen cashflow data beschikbaar voor {cf_historical_year}")

        # =====================================================================
        # PROGNOSE MODUS (bestaande functionaliteit)
        # =====================================================================
        else:
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

            weeks_back = st.slider("Aantal weken terug", 4, 104, 12, key="cf_weeks_back", help="Maximaal 2 jaar (104 weken) terug")
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

            forecast_weeks = st.slider("Aantal weken vooruit", 4, 52, 12, key="cf_forecast_weeks", help="Maximaal 1 jaar (52 weken) vooruit")

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
                ),
                xaxis=dict(
                    rangeslider=dict(visible=True),
                    type="category"
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

            # =================================================================
            # COMPARISON PERIOD SELECTION
            # =================================================================
            st.markdown("#### 🔄 Vergelijkingsperiode")

            comparison_type = st.radio(
                "Vergelijk met:",
                options=[
                    "Vorige maand",
                    "Zelfde maand vorig jaar",
                    "Aangepaste periode",
                    "Gemiddelde afgelopen 3 maanden",
                    "Gemiddelde afgelopen 6 maanden",
                    "Gemiddelde afgelopen 12 maanden"
                ],
                horizontal=True,
                key="fc_comparison_type",
                help="Kies waarmee je de geselecteerde periode wilt vergelijken"
            )

            # Default values for custom period (will be overwritten if "Aangepaste periode" is selected)
            custom_compare_year = close_year - 1
            custom_compare_month = close_month
            custom_period_length = 1

            # Show custom period selectors if "Aangepaste periode" is selected
            if comparison_type == "Aangepaste periode":
                custom_col1, custom_col2, custom_col3, custom_col4 = st.columns([1, 1, 1, 1])
                with custom_col1:
                    custom_compare_year = st.selectbox(
                        "Vergelijk met jaar",
                        options=list(range(datetime.now().year, 2021, -1)),
                        key="fc_custom_compare_year"
                    )
                with custom_col2:
                    custom_compare_month = st.selectbox(
                        "Vergelijk met maand",
                        options=list(range(1, 13)),
                        format_func=lambda x: [
                            "Januari", "Februari", "Maart", "April", "Mei", "Juni",
                            "Juli", "Augustus", "September", "Oktober", "November", "December"
                        ][x - 1],
                        key="fc_custom_compare_month"
                    )
                with custom_col3:
                    # Option for multi-month comparison
                    custom_period_length = st.selectbox(
                        "Periode lengte",
                        options=[1, 2, 3, 6, 12],
                        format_func=lambda x: f"{x} maand{'en' if x > 1 else ''}",
                        key="fc_custom_period_length",
                        help="Vergelijk met een periode van meerdere maanden"
                    )
                with custom_col4:
                    st.write("")  # Placeholder for alignment

            fc_company_id = None
            if close_company != "Alle bedrijven":
                fc_company_id = [k for k, v in COMPANIES.items() if v == close_company][0]

            # Calculate period dates
            from calendar import monthrange
            period_start = f"{close_year}-{close_month:02d}-01"
            period_end_day = monthrange(close_year, close_month)[1]
            period_end = f"{close_year}-{close_month:02d}-{period_end_day:02d}"

            month_names = [
                "Januari", "Februari", "Maart", "April", "Mei", "Juni",
                "Juli", "Augustus", "September", "Oktober", "November", "December"
            ]
            period_label = f"{month_names[close_month - 1]} {close_year}"

            # Helper function to calculate period dates going back N months
            def get_period_n_months_back(year, month, months_back):
                """Calculate start and end dates for a period N months back."""
                # Go back N months
                total_months = year * 12 + month - 1 - months_back
                target_year = total_months // 12
                target_month = (total_months % 12) + 1
                start = f"{target_year}-{target_month:02d}-01"
                end_day = monthrange(target_year, target_month)[1]
                end = f"{target_year}-{target_month:02d}-{end_day:02d}"
                return start, end, target_year, target_month

            # Helper function to calculate multi-month period
            def get_multi_month_period(end_year, end_month, num_months):
                """Calculate start and end dates for a multi-month period ending at the specified month."""
                # End date is the last day of end_month
                end_day = monthrange(end_year, end_month)[1]
                end = f"{end_year}-{end_month:02d}-{end_day:02d}"
                # Start date is num_months before
                total_months = end_year * 12 + end_month - 1 - (num_months - 1)
                start_year = total_months // 12
                start_month = (total_months % 12) + 1
                start = f"{start_year}-{start_month:02d}-01"
                return start, end, start_year, start_month, end_year, end_month

            # Calculate comparison period based on selection
            is_average_comparison = comparison_type.startswith("Gemiddelde")
            avg_num_months = 1  # Default value, will be overwritten for average comparisons

            if comparison_type == "Vorige maand":
                # Default: previous month
                prev_start, prev_end, prev_year, prev_month = get_period_n_months_back(close_year, close_month, 1)
                prev_period_label = f"{month_names[prev_month - 1]} {prev_year}"

            elif comparison_type == "Zelfde maand vorig jaar":
                # Same month, previous year
                prev_year = close_year - 1
                prev_month = close_month
                prev_start = f"{prev_year}-{prev_month:02d}-01"
                prev_end_day = monthrange(prev_year, prev_month)[1]
                prev_end = f"{prev_year}-{prev_month:02d}-{prev_end_day:02d}"
                prev_period_label = f"{month_names[prev_month - 1]} {prev_year}"

            elif comparison_type == "Aangepaste periode":
                # Custom period selected by user
                prev_year = custom_compare_year
                prev_month = custom_compare_month
                num_months = custom_period_length

                if num_months == 1:
                    prev_start = f"{prev_year}-{prev_month:02d}-01"
                    prev_end_day = monthrange(prev_year, prev_month)[1]
                    prev_end = f"{prev_year}-{prev_month:02d}-{prev_end_day:02d}"
                    prev_period_label = f"{month_names[prev_month - 1]} {prev_year}"
                else:
                    # Multi-month period
                    prev_start, prev_end, start_year, start_month, end_year, end_month = get_multi_month_period(
                        prev_year, prev_month, num_months
                    )
                    prev_period_label = f"{month_names[start_month - 1]} {start_year} - {month_names[end_month - 1]} {end_year}"

            elif comparison_type in ["Gemiddelde afgelopen 3 maanden", "Gemiddelde afgelopen 6 maanden", "Gemiddelde afgelopen 12 maanden"]:
                # Average of past N months (excluding current month)
                if comparison_type == "Gemiddelde afgelopen 3 maanden":
                    num_months = 3
                elif comparison_type == "Gemiddelde afgelopen 6 maanden":
                    num_months = 6
                else:
                    num_months = 12

                # Calculate the period for the average (N months before current month)
                prev_start, _, start_year, start_month = get_period_n_months_back(close_year, close_month, num_months)
                _, prev_end, end_year, end_month = get_period_n_months_back(close_year, close_month, 1)
                prev_period_label = f"Gem. {month_names[start_month - 1]} {start_year} - {month_names[end_month - 1]} {end_year}"
                # Store num_months for later use in average calculations
                avg_num_months = num_months
            else:
                # Fallback to previous month
                prev_start, prev_end, prev_year, prev_month = get_period_n_months_back(close_year, close_month, 1)
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

            def analyze_cost_variances_with_ai(cost_variances, current_costs_grouped, prev_costs_grouped, period_label, prev_period_label):
                """Use AI to analyze cost variances and provide insights."""
                if not get_openai_key():
                    return None, "Geen OpenAI API key geconfigureerd"

                if not cost_variances:
                    return None, "Geen kostenvarianties om te analyseren"

                # Prepare data summary for AI
                variance_summary = []
                for v in cost_variances:
                    variance_summary.append({
                        "categorie": v["name"],
                        "code": v["prefix"],
                        "huidig": v["current"],
                        "vorig": v["previous"],
                        "verschil_euro": v["variance_abs"],
                        "verschil_procent": v["variance_pct"]
                    })

                # All cost categories for context
                all_costs = []
                for prefix in ["40", "41", "42", "43", "44", "45", "46", "47"]:
                    current_amount = current_costs_grouped.get(prefix, 0)
                    prev_amount = prev_costs_grouped.get(prefix, 0)
                    category_name = CATEGORY_TRANSLATIONS.get(prefix, f"Categorie {prefix}")
                    all_costs.append({
                        "categorie": category_name,
                        "code": prefix,
                        "huidig": current_amount,
                        "vorig": prev_amount
                    })

                total_current = sum(c["huidig"] for c in all_costs)
                total_prev = sum(c["vorig"] for c in all_costs)

                prompt = f"""Analyseer de volgende kostenvarianties voor een Nederlands bedrijf en geef een praktische analyse.

**Periode:** {period_label}
**Vergelijkingsperiode:** {prev_period_label}

**Totale kosten:**
- Huidige periode: €{total_current:,.2f}
- Vorige periode: €{total_prev:,.2f}
- Verschil: €{total_current - total_prev:+,.2f} ({((total_current - total_prev) / total_prev * 100) if total_prev != 0 else 0:+.1f}%)

**Alle kostencategorieën (40-47):**
{json.dumps(all_costs, indent=2, ensure_ascii=False)}

**Categorieën met grote afwijkingen (>30% en >€500):**
{json.dumps(variance_summary, indent=2, ensure_ascii=False)}

Geef een bondige analyse (max 6 bullet points) met:
1. Korte samenvatting van de kostenontwikkeling
2. De belangrijkste afwijkingen en hun impact
3. Mogelijke verklaringen voor de varianties (seizoenseffect, eenmalige kosten, structurele verandering, etc.)
4. Correlaties tussen categorieën indien van toepassing
5. Aanbevelingen voor verder onderzoek
6. Risico's of aandachtspunten

Focus op wat actionable is. Antwoord in het Nederlands."""

                messages = [
                    {"role": "system", "content": "Je bent een ervaren financial controller die kostenanalyses uitvoert voor Nederlandse bedrijven. Geef praktische, bondige analyses met focus op business impact."},
                    {"role": "user", "content": prompt}
                ]

                return call_openai(messages)

            def analyze_margin_variances_with_ai(margin_variances, current_category_data, prev_category_data, period_label, prev_period_label):
                """Use AI to analyze margin variances and provide insights."""
                if not get_openai_key():
                    return None, "Geen OpenAI API key geconfigureerd"

                if not margin_variances:
                    return None, "Geen margevarianties om te analyseren"

                # Prepare variance summary for AI
                variance_summary = []
                for v in margin_variances:
                    variance_summary.append({
                        "categorie": v["category"],
                        "huidige_marge": v["current_margin"],
                        "vorige_marge": v["prev_margin"],
                        "marge_verandering_pp": v["margin_change"],
                        "huidige_omzet": v["current_revenue"]
                    })

                # All category margins for context
                all_margins = []
                for categ, data in sorted(current_category_data.items(), key=lambda x: x[1]["revenue"], reverse=True)[:15]:
                    current_revenue_cat = data["revenue"]
                    current_cogs_cat = data["cogs"]
                    current_margin = ((current_revenue_cat - current_cogs_cat) / current_revenue_cat * 100) if current_revenue_cat > 0 else 0

                    prev_data = prev_category_data.get(categ, {"revenue": 0, "cogs": 0})
                    prev_revenue_cat = prev_data["revenue"]
                    prev_margin = ((prev_revenue_cat - prev_data["cogs"]) / prev_revenue_cat * 100) if prev_revenue_cat > 0 else 0

                    if current_revenue_cat > 100:
                        all_margins.append({
                            "categorie": categ[:40],
                            "omzet": current_revenue_cat,
                            "kostprijs": current_cogs_cat,
                            "huidige_marge": round(current_margin, 1),
                            "vorige_marge": round(prev_margin, 1)
                        })

                total_revenue = sum(d["revenue"] for d in current_category_data.values())
                total_cogs = sum(d["cogs"] for d in current_category_data.values())
                overall_margin = ((total_revenue - total_cogs) / total_revenue * 100) if total_revenue > 0 else 0

                prev_total_revenue = sum(d["revenue"] for d in prev_category_data.values())
                prev_total_cogs = sum(d["cogs"] for d in prev_category_data.values())
                prev_overall_margin = ((prev_total_revenue - prev_total_cogs) / prev_total_revenue * 100) if prev_total_revenue > 0 else 0

                prompt = f"""Analyseer de volgende margevarianties per productcategorie voor een Nederlands bedrijf en geef een praktische analyse.

**Periode:** {period_label}
**Vergelijkingsperiode:** {prev_period_label}

**Totale marge:**
- Huidige periode: {overall_margin:.1f}% (omzet €{total_revenue:,.0f}, kostprijs €{total_cogs:,.0f})
- Vorige periode: {prev_overall_margin:.1f}% (omzet €{prev_total_revenue:,.0f})
- Verschil: {overall_margin - prev_overall_margin:+.1f} procentpunt

**Overzicht productcategorieën (top 15 op omzet):**
{json.dumps(all_margins, indent=2, ensure_ascii=False)}

**Categorieën met grote margewijzigingen (>10pp en omzet >€1000):**
{json.dumps(variance_summary, indent=2, ensure_ascii=False)}

Geef een bondige analyse (max 6 bullet points) met:
1. Korte samenvatting van de margeontwikkeling
2. De belangrijkste margewijzigingen en hun impact op het totaalresultaat
3. Mogelijke verklaringen (prijswijzigingen, inkoopkostenstijging, productmix, etc.)
4. Categorieën die extra aandacht verdienen
5. Aanbevelingen voor pricing of inkoop
6. Risico's of kansen

Focus op wat actionable is voor pricing en margeverbetering. Antwoord in het Nederlands."""

                messages = [
                    {"role": "system", "content": "Je bent een ervaren financial controller gespecialiseerd in marge-analyses voor Nederlandse bedrijven. Geef praktische, bondige analyses met focus op pricing en winstgevendheid."},
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
                prev_revenue_raw = get_period_revenue(prev_start, prev_end, fc_company_id)
                prev_costs_raw = get_period_costs(prev_start, prev_end, fc_company_id)

                # For average comparisons, divide by number of months
                if is_average_comparison:
                    prev_revenue = prev_revenue_raw / avg_num_months
                    prev_costs = prev_costs_raw / avg_num_months
                else:
                    prev_revenue = prev_revenue_raw
                    prev_costs = prev_costs_raw
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

            # Create short comparison label for metrics
            if comparison_type == "Vorige maand":
                comparison_short_label = "vs vorige maand"
            elif comparison_type == "Zelfde maand vorig jaar":
                comparison_short_label = f"vs {prev_period_label}"
            elif comparison_type == "Aangepaste periode":
                comparison_short_label = f"vs {prev_period_label}"
            elif is_average_comparison:
                comparison_short_label = f"vs {prev_period_label}"
            else:
                comparison_short_label = "vs vorige maand"

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric(
                    "📈 Omzet",
                    f"€{current_revenue:,.0f}",
                    delta=f"{revenue_pct:+.1f}% {comparison_short_label}"
                )
            with col2:
                st.metric(
                    "📉 Kosten",
                    f"€{current_costs:,.0f}",
                    delta=f"{costs_pct:+.1f}% {comparison_short_label}",
                    delta_color="inverse"
                )
            with col3:
                st.metric(
                    "💵 Resultaat",
                    f"€{current_profit:,.0f}",
                    delta=f"{profit_pct:+.1f}% {comparison_short_label}"
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

            # For average comparisons, divide previous period costs by number of months
            if is_average_comparison:
                for prefix in prev_costs_grouped:
                    prev_costs_grouped[prefix] = prev_costs_grouped[prefix] / avg_num_months

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

            # For average comparisons, divide previous period category data by number of months
            if is_average_comparison:
                for categ in prev_category_data:
                    prev_category_data[categ]["revenue"] = prev_category_data[categ]["revenue"] / avg_num_months
                    prev_category_data[categ]["cogs"] = prev_category_data[categ]["cogs"] / avg_num_months

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

                    # AI Analysis button for cost variances
                    if st.button("🤖 AI Analyse Kostenvarianties", key="cost_variance_ai_analysis", help="Laat AI de kostenvarianties analyseren"):
                        st.session_state.show_cost_variance_ai_analysis = True

                    # Show AI Analysis if requested
                    if st.session_state.get("show_cost_variance_ai_analysis", False):
                        with st.spinner("🤖 AI analyseert kostenvarianties..."):
                            ai_response, ai_error = analyze_cost_variances_with_ai(
                                cost_variances,
                                current_costs_grouped,
                                prev_costs_grouped,
                                period_label,
                                prev_period_label
                            )

                        if ai_error:
                            st.error(f"❌ AI Analyse fout: {ai_error}")
                        elif ai_response:
                            st.markdown("---")
                            st.markdown("### 🤖 AI Kostenvariantie Analyse")
                            st.markdown(ai_response)
                            if st.button("🔄 Verberg analyse", key="hide_cost_variance_analysis"):
                                st.session_state.show_cost_variance_ai_analysis = False
                                st.rerun()
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

                            # AI Analysis button for margin variances
                            if st.button("🤖 AI Analyse Margevarianties", key="margin_variance_ai_analysis", help="Laat AI de margevarianties analyseren"):
                                st.session_state.show_margin_variance_ai_analysis = True

                            # Show AI Analysis if requested
                            if st.session_state.get("show_margin_variance_ai_analysis", False):
                                with st.spinner("🤖 AI analyseert margevarianties..."):
                                    ai_response, ai_error = analyze_margin_variances_with_ai(
                                        margin_variances,
                                        current_category_data,
                                        prev_category_data,
                                        period_label,
                                        prev_period_label
                                    )

                                if ai_error:
                                    st.error(f"❌ AI Analyse fout: {ai_error}")
                                elif ai_response:
                                    st.markdown("---")
                                    st.markdown("### 🤖 AI Margevariantie Analyse")
                                    st.markdown(ai_response)
                                    if st.button("🔄 Verberg analyse", key="hide_margin_variance_analysis"):
                                        st.session_state.show_margin_variance_ai_analysis = False
                                        st.rerun()
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
Vergelijking met: {prev_period_label}
Entiteit: {close_company}

FINANCIËLE KERNCIJFERS
----------------------
Omzet:      €{current_revenue:,.0f} ({revenue_pct:+.1f}% {comparison_short_label})
Kosten:     €{current_costs:,.0f} ({costs_pct:+.1f}% {comparison_short_label})
Resultaat:  €{current_profit:,.0f} ({profit_pct:+.1f}% {comparison_short_label})
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

    # =========================================================================
    # TAB 11: FINANCIAL FORECAST
    # =========================================================================
    with tabs[10]:
        st.header("🔮 Financial Forecast")
        st.caption("Maak financiële prognoses en vergelijk met actuele resultaten")

        # Initialize forecast session state
        if "current_forecast" not in st.session_state:
            st.session_state.current_forecast = None
        if "forecast_mode" not in st.session_state:
            st.session_state.forecast_mode = "new"  # 'new', 'edit', 'compare'

        # Subtabs for forecast module
        forecast_subtabs = st.tabs([
            "📝 Invoer / Scenario",
            "📊 Resultaten",
            "📈 Forecast vs Actueel",
            "💾 Opgeslagen Forecasts"
        ])

        # =====================================================================
        # SUBTAB 1: INPUT / SCENARIO SELECTION
        # =====================================================================
        with forecast_subtabs[0]:
            st.subheader("📝 Forecast Invoer")

            # Sidebar-like controls at top
            ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4 = st.columns([2, 2, 2, 2])

            with ctrl_col1:
                time_period = st.selectbox(
                    "Prognose Periode",
                    options=[3, 6, 12, 18, 24, 36, 48, 60],
                    index=2,
                    format_func=lambda x: f"{x} maanden ({x//12} jaar)" if x >= 12 and x % 12 == 0 else f"{x} maanden",
                    help="Selecteer de periode voor de prognose (tot 5 jaar)"
                )

            with ctrl_col2:
                forecast_company = st.selectbox(
                    "Bedrijf",
                    options=[None, 1, 2, 3],
                    format_func=lambda x: "Alle bedrijven" if x is None else COMPANIES.get(x, f"ID {x}"),
                    help="Selecteer het bedrijf voor de prognose"
                )

            with ctrl_col3:
                # Start period selection
                current_year = datetime.now().year
                start_col1, start_col2 = st.columns(2)
                with start_col1:
                    forecast_start_month = st.selectbox(
                        "Start maand",
                        options=list(range(1, 13)),
                        index=datetime.now().month - 1,
                        format_func=lambda x: DUTCH_MONTHS.get(x, f"Maand {x}"),
                        key="forecast_start_month"
                    )
                with start_col2:
                    forecast_start_year = st.selectbox(
                        "Start jaar",
                        options=list(range(current_year - 2, current_year + 5)),
                        index=2,  # Current year
                        key="forecast_start_year"
                    )

            with ctrl_col4:
                if st.button("🆕 Nieuwe Forecast", type="primary"):
                    st.session_state.current_forecast = create_empty_forecast(
                        company_id=forecast_company,
                        time_period_months=time_period,
                        start_month=forecast_start_month,
                        start_year=forecast_start_year
                    )
                    st.session_state.forecast_mode = "new"
                    st.rerun()

            st.markdown("---")

            # Scenario Templates Section
            st.subheader("🎯 Scenario Templates")
            st.caption("Klik op een scenario om automatisch waarden in te vullen")

            # Account Mapping Configuration - NEW DRAGGABLE TOOL
            with st.expander("🔄 Sleepbare Rekening Mapping (Nieuw!)", expanded=False):
                st.caption("Wijs rekeningen toe aan rapportage categorieën voor je eigen financiële rapportage structuur")
                st.info("""
                **Nieuwe Rapportage Structuur:**
                - **Netto Omzet** → Kostprijs → Prijsverschillen → Overige inkoopkosten → Voorraadaanpassingen = **Bruto Omzet Resultaat**
                - **Operationele Kosten:** Lonen, Personeel, Management Fee, Huisvesting, Verkoop, IT, Vervoer, Kantoor, Admin, Algemeen
                - **Overige:** Financieel resultaat, Afschrijvingen
                - **Resultaat voor Belasting** → Belastingen → **Resultaat na Belasting**
                """)

                # Get year for account discovery - allow user to select
                current_year = datetime.now().year
                mapping_year_options = list(range(current_year - 5, current_year + 1))
                mapping_year = st.selectbox(
                    "Jaar voor rekeningen ophalen",
                    options=mapping_year_options,
                    index=len(mapping_year_options) - 2,  # Default to previous year
                    key="mapping_year_select",
                    help="Selecteer het jaar waarvan de rekeningen opgehaald moeten worden"
                )
                render_draggable_mapping_tool(forecast_company, mapping_year)

            # Legacy Account Mapping Configuration (collapsed by default)
            with st.expander("⚙️ Oude Rekening Mapping (Legacy)", expanded=False):
                st.caption("Configureer welke rekeningen gebruikt worden voor omzet, COGS en kosten (oude methode)")

                # Initialize mapping in session_state if not exists
                if "forecast_account_mapping" not in st.session_state:
                    st.session_state.forecast_account_mapping = DEFAULT_ACCOUNT_MAPPING.copy()

                mapping = st.session_state.forecast_account_mapping

                map_col1, map_col2 = st.columns(2)

                with map_col1:
                    st.markdown("**Omzet Rekeningen**")
                    revenue_input = st.text_input(
                        "Rekening prefixes (komma-gescheiden)",
                        value=", ".join(mapping["revenue"]["account_patterns"]),
                        key="revenue_patterns_input",
                        help="Bijv: 70, 71, 72, 73, 74 voor Belgisch rekeningschema"
                    )

                    st.markdown("**COGS Rekeningen**")
                    cogs_input = st.text_input(
                        "Rekening prefixes (komma-gescheiden)",
                        value=", ".join(mapping["cogs"]["account_patterns"]),
                        key="cogs_patterns_input",
                        help="Bijv: 60 voor aankopen/kostprijs verkopen"
                    )

                with map_col2:
                    st.markdown("**Operationele Kosten Categorieën**")
                    expense_cats_display = "\n".join([f"{k}: {v}" for k, v in EXPENSE_CATEGORIES.items()])
                    st.text_area(
                        "Huidige categorieën",
                        value=expense_cats_display,
                        height=150,
                        disabled=True,
                        help="Rekening prefixes 61-66 worden automatisch gemapt"
                    )

                # Discover accounts button
                disc_col1, disc_col2 = st.columns([1, 2])
                with disc_col1:
                    if st.button("🔍 Ontdek Rekeningen", key="discover_accounts"):
                        with st.spinner("Rekeningen analyseren..."):
                            current_year = datetime.now().year
                            account_groups = discover_account_groups(forecast_company, current_year - 1)
                            if account_groups:
                                st.session_state.discovered_accounts = account_groups

                # Show discovered accounts if available
                if "discovered_accounts" in st.session_state and st.session_state.discovered_accounts:
                    st.markdown("**Gevonden rekening groepen (vorig jaar):**")
                    acc_df_data = []
                    for prefix, info in sorted(st.session_state.discovered_accounts.items()):
                        balance = info["balance"]
                        acc_type = "Debet" if balance > 0 else "Credit"
                        acc_df_data.append({
                            "Prefix": prefix,
                            "Saldo": f"€ {abs(balance):,.0f}",
                            "Type": acc_type,
                            "Suggestie": "Omzet" if prefix.startswith("7") else ("Kosten" if prefix.startswith("6") else "Anders")
                        })
                    if acc_df_data:
                        st.dataframe(pd.DataFrame(acc_df_data), use_container_width=True, hide_index=True)

                # Save mapping button
                if st.button("💾 Mapping Opslaan", key="save_legacy_mapping"):
                    # Parse inputs
                    new_revenue = [p.strip() for p in revenue_input.split(",") if p.strip()]
                    new_cogs = [p.strip() for p in cogs_input.split(",") if p.strip()]

                    st.session_state.forecast_account_mapping["revenue"]["account_patterns"] = new_revenue
                    st.session_state.forecast_account_mapping["cogs"]["account_patterns"] = new_cogs
                    st.success("✅ Mapping opgeslagen!")
                    # Clear cache to use new mapping
                    get_base_year_data.clear()
                    st.rerun()

            # Base year selection for scenarios
            with st.expander("📅 Basisjaar Instellingen", expanded=True):
                base_year_col1, base_year_col2 = st.columns(2)
                with base_year_col1:
                    use_base_year = st.checkbox(
                        "Gebruik historische data als basis",
                        value=False,
                        key="use_base_year",
                        help="Haal de gemiddelde maandomzet en kosten op uit een historisch jaar"
                    )
                with base_year_col2:
                    current_year = datetime.now().year
                    base_year_options = list(range(current_year - 5, current_year + 1))
                    # Calculate default index based on session_state or default to previous year
                    if "base_year_select" in st.session_state and st.session_state.base_year_select in base_year_options:
                        default_index = base_year_options.index(st.session_state.base_year_select)
                    else:
                        default_index = len(base_year_options) - 2  # Previous year
                    base_year = st.selectbox(
                        "Basisjaar",
                        options=base_year_options,
                        index=default_index,
                        key="base_year_select",
                        disabled=not use_base_year,
                        help="Selecteer het jaar waarvan de historische data gebruikt moet worden"
                    )

                # Show base year data preview if enabled
                if use_base_year:
                    # Get configured account mapping
                    acct_mapping = st.session_state.get("forecast_account_mapping", DEFAULT_ACCOUNT_MAPPING)
                    revenue_patterns = acct_mapping["revenue"]["account_patterns"]
                    cogs_patterns = acct_mapping["cogs"]["account_patterns"]

                    with st.spinner(f"Ophalen data {base_year}..."):
                        base_year_data = get_base_year_data(
                            forecast_company, base_year,
                            revenue_patterns=tuple(revenue_patterns),
                            cogs_patterns=tuple(cogs_patterns),
                            expense_categories=EXPENSE_CATEGORIES
                        )
                    if base_year_data:
                        st.success(f"✅ Data van {base_year} opgehaald ({base_year_data['months_with_data']} maanden)")
                        preview_col1, preview_col2, preview_col3 = st.columns(3)
                        with preview_col1:
                            st.metric("Gem. maandomzet", f"€ {base_year_data['average_monthly_revenue']:,.0f}")
                        with preview_col2:
                            st.metric("Gem. maand COGS", f"€ {base_year_data['average_monthly_cogs']:,.0f}")
                        with preview_col3:
                            st.metric("COGS %", f"{base_year_data['cogs_percentage']*100:.1f}%")

                        # Show expense categories breakdown
                        if base_year_data.get("average_monthly_expenses"):
                            with st.expander("📊 Operationele Kosten per Categorie", expanded=False):
                                total_expenses = 0
                                expense_cols = st.columns(2)
                                expense_items = list(base_year_data["average_monthly_expenses"].items())
                                for i, (cat_code, avg_expense) in enumerate(expense_items):
                                    cat_name = EXPENSE_CATEGORIES.get(cat_code, f"Categorie {cat_code}")
                                    with expense_cols[i % 2]:
                                        if avg_expense > 0:
                                            st.metric(cat_name, f"€ {avg_expense:,.0f}/mnd")
                                            total_expenses += avg_expense
                                st.markdown("---")
                                st.metric("**Totaal Operationele Kosten**", f"€ {total_expenses:,.0f}/mnd")
                    else:
                        st.warning(f"Geen data gevonden voor {base_year}")
                        base_year_data = None
                else:
                    base_year_data = None

            scenario_cols = st.columns(3)

            for idx, (key, template) in enumerate(SCENARIO_TEMPLATES.items()):
                with scenario_cols[idx]:
                    with st.container(border=True):
                        st.markdown(f"### {template['icon']} {template['name']}")
                        st.caption(template['description'])

                        # Editable percentage inputs
                        with st.expander("📊 Percentages aanpassen", expanded=False):
                            custom_growth = st.number_input(
                                "Groei % per maand",
                                min_value=-50.0,
                                max_value=100.0,
                                value=float(template['revenue_growth_rate'] * 100),
                                step=0.5,
                                key=f"growth_{key}",
                                help="Maandelijkse omzetgroei in procent"
                            )
                            custom_cogs = st.number_input(
                                "COGS % van omzet",
                                min_value=0.0,
                                max_value=100.0,
                                value=float(template['cogs_percentage'] * 100),
                                step=1.0,
                                key=f"cogs_{key}",
                                help="Kostprijs verkopen als percentage van omzet"
                            )
                            custom_expense = st.number_input(
                                "Kosten aanpassing %",
                                min_value=-50.0,
                                max_value=100.0,
                                value=float((template['expense_multiplier'] - 1) * 100),
                                step=1.0,
                                key=f"expense_{key}",
                                help="Aanpassing van operationele kosten (0% = ongewijzigd)"
                            )

                        # Show current settings
                        st.markdown(f"""
                        - **Groei:** {custom_growth:.1f}% per maand
                        - **COGS:** {custom_cogs:.0f}% van omzet
                        - **Kosten:** {'+' if custom_expense >= 0 else ''}{custom_expense:.0f}%
                        """)

                        # Base revenue input for this scenario (only if not using base year)
                        if not use_base_year:
                            base_rev = st.number_input(
                                "Basis omzet/maand (€)",
                                min_value=0,
                                value=100000,
                                step=10000,
                                key=f"base_rev_{key}",
                                help="Startwaarde voor maandelijkse omzet"
                            )
                        else:
                            if base_year_data:
                                base_rev = base_year_data["average_monthly_revenue"]
                                st.info(f"Basis: € {base_rev:,.0f}/maand ({base_year})")
                            else:
                                base_rev = 100000

                        if st.button(f"Toepassen {template['name']}", key=f"apply_{key}"):
                            forecast = create_empty_forecast(
                                company_id=forecast_company,
                                time_period_months=time_period,
                                start_month=forecast_start_month,
                                start_year=forecast_start_year
                            )
                            forecast["name"] = f"{template['name']} Scenario"
                            # Store base year info in forecast if used
                            if use_base_year and base_year_data:
                                forecast["base_year"] = base_year
                                forecast["base_year_data"] = base_year_data
                                forecast = apply_scenario_template(
                                    forecast, key,
                                    base_revenue=base_year_data["average_monthly_revenue"],
                                    base_expenses=base_year_data["average_monthly_expenses"],
                                    custom_growth_rate=custom_growth / 100,
                                    custom_cogs_percentage=custom_cogs / 100,
                                    custom_expense_multiplier=1 + (custom_expense / 100)
                                )
                            else:
                                forecast = apply_scenario_template(
                                    forecast, key,
                                    base_revenue=base_rev,
                                    custom_growth_rate=custom_growth / 100,
                                    custom_cogs_percentage=custom_cogs / 100,
                                    custom_expense_multiplier=1 + (custom_expense / 100)
                                )
                            st.session_state.current_forecast = forecast
                            st.success(f"✅ {template['name']} scenario toegepast!")
                            st.rerun()

            st.markdown("---")

            # Use Previous Year Actuals as Basis
            st.subheader("📅 Basis op Vorig Jaar Actuals")
            st.caption("Laad de werkelijke cijfers van vorig jaar als startpunt voor je forecast")

            with st.container(border=True):
                actuals_cols = st.columns([2, 1, 1, 1])
                with actuals_cols[0]:
                    st.markdown("**Gebruik actuele cijfers van vorig jaar**")
                    st.caption("Haalt de werkelijke omzet, kosten en categorieën op uit Odoo voor dezelfde periode vorig jaar")
                with actuals_cols[1]:
                    growth_adjustment = st.number_input(
                        "Groei aanpassing (%)",
                        min_value=-50.0,
                        max_value=100.0,
                        value=5.0,
                        step=1.0,
                        key="actuals_growth_adj",
                        help="Pas groei toe op de cijfers van vorig jaar (bijv. 5% = vorig jaar + 5%)"
                    )
                with actuals_cols[2]:
                    cost_adjustment = st.number_input(
                        "Kosten aanpassing (%)",
                        min_value=-50.0,
                        max_value=100.0,
                        value=3.0,
                        step=1.0,
                        key="actuals_cost_adj",
                        help="Pas aanpassing toe op kosten (bijv. 3% = verwachte kostenstijging)"
                    )
                with actuals_cols[3]:
                    st.markdown("&nbsp;")  # Spacer
                    if st.button("📥 Laad Vorig Jaar", type="secondary", key="load_prev_year"):
                        # Calculate previous year period
                        today = datetime.today()
                        prev_year_start = datetime(today.year - 1, today.month, 1)
                        start_date_str = prev_year_start.strftime("%Y-%m-%d")

                        # Get configured account mapping from user's report structure
                        acct_mapping = st.session_state.get("forecast_account_mapping", DEFAULT_ACCOUNT_MAPPING)
                        revenue_patterns = acct_mapping["revenue"]["account_patterns"]
                        cogs_patterns = acct_mapping["cogs"]["account_patterns"]

                        # Get actuals from previous year using user's configured mapping
                        prev_year_actuals = get_actual_data_for_comparison(
                            company_id=forecast_company,
                            start_date=start_date_str,
                            num_months=time_period,
                            revenue_patterns=revenue_patterns,
                            cogs_patterns=cogs_patterns
                        )

                        if prev_year_actuals:
                            # Create new forecast based on previous year actuals
                            forecast = create_empty_forecast(
                                company_id=forecast_company,
                                time_period_months=time_period
                            )
                            forecast["name"] = f"Forecast o.b.v. actuals {today.year - 1}"
                            forecast["description"] = f"Gebaseerd op werkelijke cijfers van {today.year - 1} met {growth_adjustment}% groei en {cost_adjustment}% kostenaanpassing"

                            # Apply growth adjustment to revenue
                            growth_factor = 1 + (growth_adjustment / 100)
                            for i, rev_val in enumerate(prev_year_actuals.get("revenue", [])):
                                if i < len(forecast["revenue"]["values"]):
                                    forecast["revenue"]["values"][i] = rev_val * growth_factor

                            # Apply cost adjustment to COGS
                            cost_factor = 1 + (cost_adjustment / 100)
                            for i, cogs_val in enumerate(prev_year_actuals.get("cogs", [])):
                                if i < len(forecast["cogs"]["values"]):
                                    forecast["cogs"]["values"][i] = cogs_val * cost_factor

                            # Apply cost adjustment to operating expenses by category
                            for cat_code, cat_values in prev_year_actuals.get("operating_expenses", {}).items():
                                if cat_code in forecast["operating_expenses"]:
                                    for i, exp_val in enumerate(cat_values):
                                        if i < len(forecast["operating_expenses"][cat_code]["values"]):
                                            forecast["operating_expenses"][cat_code]["values"][i] = exp_val * cost_factor
                                            # Also update session state for the input widgets
                                            widget_key = f"exp_{cat_code}_{i}"
                                            if widget_key in st.session_state:
                                                st.session_state[widget_key] = exp_val * cost_factor

                            st.session_state.current_forecast = forecast
                            st.success(f"✅ Actuals van {today.year - 1} geladen als basis! Groei: {growth_adjustment}%, Kosten: +{cost_adjustment}%")
                            st.rerun()
                        else:
                            st.error("❌ Kon geen actuele data ophalen van vorig jaar. Controleer de Odoo connectie.")

            st.markdown("---")

            # Manual Input Section
            st.subheader("✏️ Handmatige Invoer")

            if st.session_state.current_forecast is None:
                st.info("👆 Selecteer een scenario hierboven, laad vorig jaar actuals, of klik op 'Nieuwe Forecast' om te beginnen")
            else:
                forecast = st.session_state.current_forecast
                periods = forecast.get("periods", [])

                # Forecast metadata
                with st.expander("📋 Forecast Informatie", expanded=True):
                    meta_col1, meta_col2 = st.columns(2)
                    with meta_col1:
                        forecast["name"] = st.text_input(
                            "Forecast Naam *",
                            value=forecast.get("name", ""),
                            help="Geef een duidelijke naam aan deze prognose"
                        )
                    with meta_col2:
                        forecast["description"] = st.text_input(
                            "Beschrijving",
                            value=forecast.get("description", ""),
                            help="Optionele beschrijving of notities"
                        )

                # Revenue Input
                with st.expander("💰 Omzet Projecties", expanded=True):
                    rev_input_type = st.radio(
                        "Invoermethode",
                        options=["Absolute waarden", "Groeipercentage"],
                        horizontal=True,
                        key="rev_input_type"
                    )

                    if rev_input_type == "Groeipercentage":
                        growth_cols = st.columns(2)
                        with growth_cols[0]:
                            base_revenue = st.number_input(
                                "Basis omzet maand 1 (€)",
                                min_value=0.0,
                                value=float(forecast["revenue"]["values"][0]) if forecast["revenue"]["values"][0] > 0 else 100000.0,
                                step=1000.0
                            )
                        with growth_cols[1]:
                            growth_rate = st.number_input(
                                "Maandelijkse groei (%)",
                                min_value=-50.0,
                                max_value=100.0,
                                value=forecast["revenue"]["growth_rate"],
                                step=0.5
                            )
                        # Apply growth
                        forecast["revenue"]["input_type"] = "growth"
                        forecast["revenue"]["growth_rate"] = growth_rate
                        for i in range(len(forecast["revenue"]["values"])):
                            forecast["revenue"]["values"][i] = base_revenue * ((1 + growth_rate/100) ** i)
                    else:
                        forecast["revenue"]["input_type"] = "absolute"
                        # Show input for each period (max 6 columns per row)
                        num_cols = min(6, len(periods))
                        for row_start in range(0, len(periods), num_cols):
                            row_periods = periods[row_start:row_start + num_cols]
                            cols = st.columns(len(row_periods))
                            for col_idx, period in enumerate(row_periods):
                                period_idx = row_start + col_idx
                                with cols[col_idx]:
                                    label = period["label"][:3] + " " + str(period["year"])[-2:]
                                    forecast["revenue"]["values"][period_idx] = st.number_input(
                                        label,
                                        min_value=0.0,
                                        value=float(forecast["revenue"]["values"][period_idx]),
                                        step=1000.0,
                                        key=f"rev_{period_idx}"
                                    )

                # Initialize expenses dict if not present (for backwards compatibility)
                if "expenses" not in forecast:
                    forecast["expenses"] = {}
                    for code, name in FORECAST_EXPENSE_CATEGORIES.items():
                        forecast["expenses"][code] = {
                            "name": name,
                            "values": [0.0] * len(periods),
                            "growth_rate": 0.0,
                            "notes": ""
                        }

                # ============================================================
                # NEW EXPENSE INPUT STRUCTURE (matches mapping tool)
                # ============================================================

                # Quick-fill helper function
                def quick_fill_category(cat_code, amount):
                    if cat_code in forecast["expenses"]:
                        for i in range(len(forecast["expenses"][cat_code]["values"])):
                            forecast["expenses"][cat_code]["values"][i] = amount
                        st.session_state.current_forecast = forecast
                        st.rerun()

                # Section 1: Kostprijs & Inkoop
                with st.expander("📦 Kostprijs & Inkoop", expanded=False):
                    st.caption("Kostprijs van de omzet en gerelateerde inkoopkosten")

                    # Quick-fill for this section
                    qf_col1, qf_col2, qf_col3 = st.columns([2, 1, 1])
                    with qf_col1:
                        cost_cats = FORECAST_CATEGORY_GROUPS["cost_of_sales"]["categories"]
                        selected_cost_cat = st.selectbox(
                            "Categorie",
                            options=cost_cats,
                            format_func=lambda x: FORECAST_EXPENSE_CATEGORIES.get(x, x),
                            key="qf_cost_cat"
                        )
                    with qf_col2:
                        qf_cost_amount = st.number_input("Maandelijks", min_value=0.0, value=5000.0, step=500.0, key="qf_cost_amount")
                    with qf_col3:
                        if st.button("Vul in", key="qf_cost_btn"):
                            quick_fill_category(selected_cost_cat, qf_cost_amount)

                    st.markdown("---")

                    for cat_code in FORECAST_CATEGORY_GROUPS["cost_of_sales"]["categories"]:
                        cat_name = FORECAST_EXPENSE_CATEGORIES.get(cat_code, cat_code)
                        cat_data = forecast["expenses"].get(cat_code, {"values": [0.0] * len(periods)})

                        with st.expander(f"{cat_name}", expanded=False):
                            num_cols = min(6, len(periods))
                            for row_start in range(0, len(periods), num_cols):
                                row_periods = periods[row_start:row_start + num_cols]
                                cols = st.columns(len(row_periods))
                                for col_idx, period in enumerate(row_periods):
                                    period_idx = row_start + col_idx
                                    with cols[col_idx]:
                                        label = period["label"][:3] + " " + str(period["year"])[-2:]
                                        cat_data["values"][period_idx] = st.number_input(
                                            label,
                                            min_value=0.0,
                                            value=float(cat_data["values"][period_idx]),
                                            step=100.0,
                                            key=f"new_exp_{cat_code}_{period_idx}"
                                        )
                        forecast["expenses"][cat_code] = cat_data

                # Section 2: Operationele Kosten
                with st.expander("⚙️ Operationele Kosten", expanded=False):
                    st.caption("Lonen, personeel, huisvesting, verkoop, IT en overige operationele kosten")

                    # Quick-fill for this section
                    qf_col1, qf_col2, qf_col3 = st.columns([2, 1, 1])
                    with qf_col1:
                        op_cats = FORECAST_CATEGORY_GROUPS["operating_expenses"]["categories"]
                        selected_op_cat = st.selectbox(
                            "Categorie",
                            options=op_cats,
                            format_func=lambda x: FORECAST_EXPENSE_CATEGORIES.get(x, x),
                            key="qf_op_cat"
                        )
                    with qf_col2:
                        qf_op_amount = st.number_input("Maandelijks", min_value=0.0, value=5000.0, step=500.0, key="qf_op_amount")
                    with qf_col3:
                        if st.button("Vul in", key="qf_op_btn"):
                            quick_fill_category(selected_op_cat, qf_op_amount)

                    st.markdown("---")

                    for cat_code in FORECAST_CATEGORY_GROUPS["operating_expenses"]["categories"]:
                        cat_name = FORECAST_EXPENSE_CATEGORIES.get(cat_code, cat_code)
                        cat_data = forecast["expenses"].get(cat_code, {"values": [0.0] * len(periods)})

                        with st.expander(f"{cat_name}", expanded=False):
                            num_cols = min(6, len(periods))
                            for row_start in range(0, len(periods), num_cols):
                                row_periods = periods[row_start:row_start + num_cols]
                                cols = st.columns(len(row_periods))
                                for col_idx, period in enumerate(row_periods):
                                    period_idx = row_start + col_idx
                                    with cols[col_idx]:
                                        label = period["label"][:3] + " " + str(period["year"])[-2:]
                                        cat_data["values"][period_idx] = st.number_input(
                                            label,
                                            min_value=0.0,
                                            value=float(cat_data["values"][period_idx]),
                                            step=100.0,
                                            key=f"new_exp_{cat_code}_{period_idx}"
                                        )
                        forecast["expenses"][cat_code] = cat_data

                # Section 3: Overige Lasten & Opbrengsten
                with st.expander("📊 Overige Lasten & Opbrengsten", expanded=False):
                    st.caption("Financieel resultaat en afschrijvingen")

                    for cat_code in FORECAST_CATEGORY_GROUPS["other_expenses"]["categories"]:
                        cat_name = FORECAST_EXPENSE_CATEGORIES.get(cat_code, cat_code)
                        cat_data = forecast["expenses"].get(cat_code, {"values": [0.0] * len(periods)})

                        with st.expander(f"{cat_name}", expanded=False):
                            num_cols = min(6, len(periods))
                            for row_start in range(0, len(periods), num_cols):
                                row_periods = periods[row_start:row_start + num_cols]
                                cols = st.columns(len(row_periods))
                                for col_idx, period in enumerate(row_periods):
                                    period_idx = row_start + col_idx
                                    with cols[col_idx]:
                                        label = period["label"][:3] + " " + str(period["year"])[-2:]
                                        cat_data["values"][period_idx] = st.number_input(
                                            label,
                                            min_value=0.0,
                                            value=float(cat_data["values"][period_idx]),
                                            step=100.0,
                                            key=f"new_exp_{cat_code}_{period_idx}"
                                        )
                        forecast["expenses"][cat_code] = cat_data

                # Section 4: Belastingen
                with st.expander("🏛️ Belastingen", expanded=False):
                    st.caption("Vennootschapsbelasting en overige belastingen")

                    for cat_code in FORECAST_CATEGORY_GROUPS["taxes"]["categories"]:
                        cat_name = FORECAST_EXPENSE_CATEGORIES.get(cat_code, cat_code)
                        cat_data = forecast["expenses"].get(cat_code, {"values": [0.0] * len(periods)})

                        num_cols = min(6, len(periods))
                        for row_start in range(0, len(periods), num_cols):
                            row_periods = periods[row_start:row_start + num_cols]
                            cols = st.columns(len(row_periods))
                            for col_idx, period in enumerate(row_periods):
                                period_idx = row_start + col_idx
                                with cols[col_idx]:
                                    label = period["label"][:3] + " " + str(period["year"])[-2:]
                                    cat_data["values"][period_idx] = st.number_input(
                                        label,
                                        min_value=0.0,
                                        value=float(cat_data["values"][period_idx]),
                                        step=100.0,
                                        key=f"new_exp_{cat_code}_{period_idx}"
                                    )
                        forecast["expenses"][cat_code] = cat_data

                # LEGACY: Operating Expenses (hidden, for backwards compatibility)
                with st.expander("📉 Oude Kosten Categorieën (Legacy)", expanded=False):
                    st.caption("Oude categorieën voor backwards compatibiliteit met bestaande forecasts")

                    for code, cat_data in forecast.get("operating_expenses", {}).items():
                        with st.expander(f"{EXPENSE_CATEGORIES.get(code, code)}", expanded=False):
                            num_cols = min(6, len(periods))
                            for row_start in range(0, len(periods), num_cols):
                                row_periods = periods[row_start:row_start + num_cols]
                                cols = st.columns(len(row_periods))
                                for col_idx, period in enumerate(row_periods):
                                    period_idx = row_start + col_idx
                                    with cols[col_idx]:
                                        label = period["label"][:3] + " " + str(period["year"])[-2:]
                                        cat_data["values"][period_idx] = st.number_input(
                                            label,
                                            min_value=0.0,
                                            value=float(cat_data["values"][period_idx]),
                                            step=100.0,
                                            key=f"legacy_exp_{code}_{period_idx}"
                                        )

                # Capital Expenditures
                with st.expander("🏗️ Kapitaaluitgaven (CapEx)", expanded=False):
                    st.caption("Investeringen in vaste activa")
                    num_cols = min(6, len(periods))
                    for row_start in range(0, len(periods), num_cols):
                        row_periods = periods[row_start:row_start + num_cols]
                        cols = st.columns(len(row_periods))
                        for col_idx, period in enumerate(row_periods):
                            period_idx = row_start + col_idx
                            with cols[col_idx]:
                                label = period["label"][:3] + " " + str(period["year"])[-2:]
                                forecast["capex"]["values"][period_idx] = st.number_input(
                                    label,
                                    min_value=0.0,
                                    value=float(forecast["capex"]["values"][period_idx]),
                                    step=1000.0,
                                    key=f"capex_{period_idx}"
                                )

                # Other Income/Expenses
                with st.expander("➕ Overige Inkomsten / Uitgaven", expanded=False):
                    oth_col1, oth_col2 = st.columns(2)
                    with oth_col1:
                        st.markdown("**Overige Inkomsten**")
                        num_cols = min(4, len(periods))
                        for row_start in range(0, len(periods), num_cols):
                            row_periods = periods[row_start:row_start + num_cols]
                            cols = st.columns(len(row_periods))
                            for col_idx, period in enumerate(row_periods):
                                period_idx = row_start + col_idx
                                with cols[col_idx]:
                                    label = period["label"][:3] + " " + str(period["year"])[-2:]
                                    forecast["other_income"]["values"][period_idx] = st.number_input(
                                        label,
                                        min_value=0.0,
                                        value=float(forecast["other_income"]["values"][period_idx]),
                                        step=500.0,
                                        key=f"oth_inc_{period_idx}"
                                    )
                    with oth_col2:
                        st.markdown("**Overige Uitgaven**")
                        num_cols = min(4, len(periods))
                        for row_start in range(0, len(periods), num_cols):
                            row_periods = periods[row_start:row_start + num_cols]
                            cols = st.columns(len(row_periods))
                            for col_idx, period in enumerate(row_periods):
                                period_idx = row_start + col_idx
                                with cols[col_idx]:
                                    label = period["label"][:3] + " " + str(period["year"])[-2:]
                                    forecast["other_expenses"]["values"][period_idx] = st.number_input(
                                        label,
                                        min_value=0.0,
                                        value=float(forecast["other_expenses"]["values"][period_idx]),
                                        step=500.0,
                                        key=f"oth_exp_{period_idx}"
                                    )

                # Assumptions
                with st.expander("⚙️ Aannames & Variabelen", expanded=False):
                    st.caption("Pas deze aannames aan om de forecast te beïnvloeden")

                    assum_col1, assum_col2, assum_col3 = st.columns(3)

                    with assum_col1:
                        forecast["assumptions"]["customer_acquisition_rate"] = st.slider(
                            "Klantacquisitie Rate (%)",
                            min_value=0,
                            max_value=50,
                            value=int(forecast["assumptions"]["customer_acquisition_rate"] * 100),
                            help="Percentage nieuwe klanten per periode"
                        ) / 100

                        forecast["assumptions"]["average_transaction_value"] = st.number_input(
                            "Gem. Transactiewaarde (€)",
                            min_value=0.0,
                            value=float(forecast["assumptions"]["average_transaction_value"]),
                            step=10.0,
                            help="Gemiddelde waarde per transactie"
                        )

                    with assum_col2:
                        forecast["assumptions"]["churn_rate"] = st.slider(
                            "Churn Rate (%)",
                            min_value=0,
                            max_value=30,
                            value=int(forecast["assumptions"]["churn_rate"] * 100),
                            help="Percentage klantverloop per periode"
                        ) / 100

                        forecast["assumptions"]["average_transaction_value_growth"] = st.slider(
                            "Transactiewaarde Groei (%)",
                            min_value=-10,
                            max_value=20,
                            value=int(forecast["assumptions"]["average_transaction_value_growth"] * 100),
                            help="Jaarlijkse groei van gemiddelde transactiewaarde"
                        ) / 100

                    with assum_col3:
                        forecast["assumptions"]["inflation_rate"] = st.slider(
                            "Inflatie Rate (%)",
                            min_value=0,
                            max_value=15,
                            value=int(forecast["assumptions"]["inflation_rate"] * 100),
                            help="Jaarlijks inflatiepercentage"
                        ) / 100

                    # Seasonal Factors
                    st.markdown("**Seizoenscorrectie Factoren**")
                    st.caption("Pas per maand aan (1.0 = normaal, 1.2 = 20% hoger, 0.8 = 20% lager)")
                    season_cols = st.columns(6)
                    for i in range(12):
                        with season_cols[i % 6]:
                            forecast["assumptions"]["seasonal_factors"][i] = st.number_input(
                                DUTCH_MONTHS[i+1][:3],
                                min_value=0.5,
                                max_value=2.0,
                                value=float(forecast["assumptions"]["seasonal_factors"][i]),
                                step=0.05,
                                key=f"season_{i}"
                            )

                # One-time Events
                with st.expander("📅 Eenmalige Events", expanded=False):
                    st.caption("Voeg eenmalige inkomsten of uitgaven toe")

                    event_cols = st.columns([2, 1, 2, 1])
                    with event_cols[0]:
                        event_month = st.selectbox(
                            "Maand",
                            options=range(len(periods)),
                            format_func=lambda x: periods[x]["label"] if x < len(periods) else str(x)
                        )
                    with event_cols[1]:
                        event_type = st.selectbox("Type", options=["income", "expense"], format_func=lambda x: "Inkomst" if x == "income" else "Uitgave")
                    with event_cols[2]:
                        event_amount = st.number_input("Bedrag (€)", min_value=0.0, value=0.0, step=1000.0)
                    with event_cols[3]:
                        event_desc = st.text_input("Beschrijving", "")

                    if st.button("➕ Event Toevoegen"):
                        if event_amount > 0:
                            forecast["one_time_events"].append({
                                "month_index": event_month,
                                "type": event_type,
                                "amount": event_amount,
                                "description": event_desc
                            })
                            st.success("Event toegevoegd!")
                            st.rerun()

                    # Display existing events
                    if forecast["one_time_events"]:
                        st.markdown("**Geplande Events:**")
                        for idx, event in enumerate(forecast["one_time_events"]):
                            event_col1, event_col2 = st.columns([4, 1])
                            with event_col1:
                                icon = "💰" if event["type"] == "income" else "💸"
                                period_label = periods[event["month_index"]]["label"] if event["month_index"] < len(periods) else "?"
                                st.write(f"{icon} {period_label}: €{event['amount']:,.0f} - {event['description']}")
                            with event_col2:
                                if st.button("🗑️", key=f"del_event_{idx}"):
                                    forecast["one_time_events"].pop(idx)
                                    st.rerun()

                # Update session state
                st.session_state.current_forecast = forecast

                # Save/Validate buttons
                st.markdown("---")
                action_col1, action_col2, action_col3 = st.columns(3)

                with action_col1:
                    if st.button("✅ Valideer Forecast", type="secondary"):
                        is_valid, warnings, errors = validate_forecast(forecast)
                        if errors:
                            for err in errors:
                                st.error(f"❌ {err}")
                        if warnings:
                            for warn in warnings:
                                st.warning(f"⚠️ {warn}")
                        if is_valid and not warnings:
                            st.success("✅ Forecast is compleet en valide!")

                with action_col2:
                    if st.button("💾 Opslaan", type="primary"):
                        is_valid, warnings, errors = validate_forecast(forecast)
                        if not is_valid:
                            for err in errors:
                                st.error(f"❌ {err}")
                        else:
                            success, msg = save_forecast(forecast)
                            if success:
                                st.success(f"✅ {msg}")
                            else:
                                st.error(f"❌ {msg}")

                with action_col3:
                    if st.button("🗑️ Wissen"):
                        st.session_state.current_forecast = None
                        st.rerun()

        # =====================================================================
        # SUBTAB 2: FORECAST RESULTS
        # =====================================================================
        with forecast_subtabs[1]:
            st.subheader("📊 Forecast Resultaten")

            if st.session_state.current_forecast is None:
                st.info("👈 Maak eerst een forecast aan in het 'Invoer / Scenario' tabblad")
            else:
                forecast = st.session_state.current_forecast
                calculated = calculate_forecast_metrics(forecast)
                periods = forecast.get("periods", [])

                if not calculated:
                    st.warning("Geen berekeningen beschikbaar - controleer invoergegevens")
                else:
                    # Key Metrics Summary
                    st.markdown("### 🎯 Kerncijfers")
                    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)

                    with kpi_col1:
                        st.metric(
                            "💰 Totale Omzet",
                            f"€{calculated['total_revenue']:,.0f}",
                            help="Som van alle maandelijkse omzet"
                        )
                    with kpi_col2:
                        st.metric(
                            "📈 Brutowinst",
                            f"€{calculated['total_gross_profit']:,.0f}",
                            delta=f"{calculated['avg_gross_margin']:.1f}% marge"
                        )
                    with kpi_col3:
                        st.metric(
                            "💵 EBITDA",
                            f"€{calculated['total_ebitda']:,.0f}",
                            help="Winst voor rente, belastingen, afschrijvingen"
                        )
                    with kpi_col4:
                        result_color = "normal" if calculated['total_net_income'] >= 0 else "inverse"
                        st.metric(
                            "🎯 Netto Resultaat",
                            f"€{calculated['total_net_income']:,.0f}",
                            delta=f"{calculated['avg_net_margin']:.1f}% marge"
                        )

                    st.markdown("---")

                    # Revenue & Profit Chart
                    st.markdown("### 📈 Omzet & Winstgevendheid")

                    period_labels = [p["label"] for p in periods]

                    fig_revenue = go.Figure()

                    # Revenue bars
                    fig_revenue.add_trace(go.Bar(
                        x=period_labels,
                        y=calculated["revenue"],
                        name="Omzet",
                        marker_color="#1e3a5f"
                    ))

                    # Gross profit bars
                    fig_revenue.add_trace(go.Bar(
                        x=period_labels,
                        y=calculated["gross_profit"],
                        name="Brutowinst",
                        marker_color="#2ecc71"
                    ))

                    # Net income line
                    fig_revenue.add_trace(go.Scatter(
                        x=period_labels,
                        y=calculated["net_income"],
                        name="Netto Resultaat",
                        mode="lines+markers",
                        line=dict(color="#e74c3c", width=3),
                        marker=dict(size=8)
                    ))

                    fig_revenue.update_layout(
                        barmode="group",
                        height=400,
                        legend=dict(orientation="h", yanchor="bottom", y=1.02),
                        yaxis=dict(title="Bedrag (€)", tickformat=",.0f"),
                        xaxis=dict(title="Periode")
                    )
                    st.plotly_chart(fig_revenue, use_container_width=True)

                    # Margins Chart
                    margin_col1, margin_col2 = st.columns(2)

                    with margin_col1:
                        fig_margin = go.Figure()
                        fig_margin.add_trace(go.Scatter(
                            x=period_labels,
                            y=calculated["gross_margin"],
                            name="Brutomarge %",
                            mode="lines+markers",
                            line=dict(color="#3498db", width=2)
                        ))
                        fig_margin.add_trace(go.Scatter(
                            x=period_labels,
                            y=calculated["ebit_margin"],
                            name="EBIT Marge %",
                            mode="lines+markers",
                            line=dict(color="#9b59b6", width=2)
                        ))
                        fig_margin.add_trace(go.Scatter(
                            x=period_labels,
                            y=calculated["net_margin"],
                            name="Netto Marge %",
                            mode="lines+markers",
                            line=dict(color="#e74c3c", width=2)
                        ))
                        fig_margin.update_layout(
                            title="Marges (%)",
                            height=300,
                            yaxis=dict(title="Percentage", ticksuffix="%"),
                            legend=dict(orientation="h", yanchor="bottom", y=1.02)
                        )
                        st.plotly_chart(fig_margin, use_container_width=True)

                    with margin_col2:
                        # Operating Expenses Breakdown (last period)
                        exp_names = []
                        exp_values = []
                        for code, cat_data in forecast["operating_expenses"].items():
                            total = sum(cat_data["values"])
                            if total > 0:
                                exp_names.append(cat_data["name"])
                                exp_values.append(total)

                        if exp_values:
                            fig_exp = px.pie(
                                values=exp_values,
                                names=exp_names,
                                title="Verdeling Operationele Kosten",
                                hole=0.4
                            )
                            fig_exp.update_layout(height=300)
                            st.plotly_chart(fig_exp, use_container_width=True)

                    # Cumulative Chart
                    st.markdown("### 📊 Cumulatief Verloop")
                    fig_cumulative = go.Figure()
                    fig_cumulative.add_trace(go.Scatter(
                        x=period_labels,
                        y=calculated["cumulative_revenue"],
                        name="Cumulatieve Omzet",
                        fill="tozeroy",
                        mode="lines",
                        line=dict(color="#1e3a5f", width=2)
                    ))
                    fig_cumulative.add_trace(go.Scatter(
                        x=period_labels,
                        y=calculated["cumulative_net_income"],
                        name="Cumulatief Resultaat",
                        fill="tozeroy",
                        mode="lines",
                        line=dict(color="#2ecc71", width=2)
                    ))
                    fig_cumulative.update_layout(
                        height=350,
                        yaxis=dict(title="Bedrag (€)", tickformat=",.0f"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02)
                    )
                    st.plotly_chart(fig_cumulative, use_container_width=True)

                    # CASHFLOW_HOOK: Display operating cash flow
                    st.markdown("### 💵 Operationele Cashflow (Indicatief)")
                    st.caption("EBITDA minus CapEx - voor gedetailleerde cashflow prognose, zie toekomstige integratie")
                    fig_cashflow = go.Figure()
                    fig_cashflow.add_trace(go.Bar(
                        x=period_labels,
                        y=calculated["operating_cash_flow"],
                        name="Operating Cash Flow",
                        marker_color=["#2ecc71" if v >= 0 else "#e74c3c" for v in calculated["operating_cash_flow"]]
                    ))
                    fig_cashflow.update_layout(
                        height=300,
                        yaxis=dict(title="Bedrag (€)", tickformat=",.0f")
                    )
                    st.plotly_chart(fig_cashflow, use_container_width=True)

                    # Detailed Data Table
                    st.markdown("### 📋 Detailoverzicht")

                    # Build summary dataframe
                    summary_data = {
                        "Periode": period_labels,
                        "Omzet": [f"€{v:,.0f}" for v in calculated["revenue"]],
                        "COGS": [f"€{v:,.0f}" for v in calculated["cogs"]],
                        "Brutowinst": [f"€{v:,.0f}" for v in calculated["gross_profit"]],
                        "Op. Kosten": [f"€{v:,.0f}" for v in calculated["operating_expenses"]],
                        "EBITDA": [f"€{v:,.0f}" for v in calculated["ebitda"]],
                        "Netto": [f"€{v:,.0f}" for v in calculated["net_income"]],
                        "Netto %": [f"{v:.1f}%" for v in calculated["net_margin"]]
                    }
                    df_summary = pd.DataFrame(summary_data)
                    st.dataframe(df_summary, use_container_width=True, hide_index=True)

                    # New Financial Report Structure (if mapping is configured)
                    with st.expander("📊 Financieel Rapport (Nieuwe Structuur)", expanded=False):
                        st.caption("Resultaten volgens de sleepbare mapping configuratie")

                        # Check if draggable mapping has been configured
                        draggable_map = get_draggable_mapping()
                        has_mapping = any(
                            accounts for accounts in draggable_map.get("categories", {}).values()
                        )

                        if not has_mapping:
                            st.info("💡 Configureer eerst de sleepbare mapping in de 'Invoer / Scenario' tab om dit rapport te gebruiken.")
                        else:
                            # Calculate using the new mapping structure
                            forecast_company_id = forecast.get("company_id")
                            forecast_start_year = forecast.get("start_year", datetime.now().year)

                            report_results = calculate_report_with_mapping(
                                forecast_company_id,
                                forecast_start_year,
                                draggable_map
                            )

                            if report_results:
                                # Display the structured report
                                st.markdown("#### Omzet & Bruto Resultaat")

                                # Revenue section
                                rev_data = []
                                revenue_cats = [
                                    "netto_omzet", "kostprijs_omzet", "prijsverschillen",
                                    "overige_inkoopkosten", "voorraadaanpassingen", "bruto_omzet_resultaat"
                                ]
                                for cat_key in revenue_cats:
                                    if cat_key in REPORT_CATEGORIES:
                                        cat_info = REPORT_CATEGORIES[cat_key]
                                        value = report_results.get(cat_key, 0)
                                        is_subtotal = cat_info.get("is_subtotal", False)
                                        rev_data.append({
                                            "Categorie": f"**{cat_info['name']}**" if is_subtotal else cat_info["name"],
                                            "Bedrag": f"€ {value:,.0f}",
                                            "Type": "Subtotaal" if is_subtotal else "Invoer"
                                        })

                                if rev_data:
                                    st.dataframe(pd.DataFrame(rev_data), use_container_width=True, hide_index=True)

                                st.markdown("---")
                                st.markdown("#### Operationele Kosten")

                                # Operating expenses section
                                op_data = []
                                op_cats = [
                                    "lonen_salarissen", "overige_personele_kosten", "management_fee",
                                    "huisvestingskosten", "verkoopkosten", "automatiseringskosten",
                                    "vervoerskosten", "kantoorkosten", "admin_accountantskosten",
                                    "algemene_kosten", "totaal_operationele_kosten"
                                ]
                                for cat_key in op_cats:
                                    if cat_key in REPORT_CATEGORIES:
                                        cat_info = REPORT_CATEGORIES[cat_key]
                                        value = report_results.get(cat_key, 0)
                                        is_subtotal = cat_info.get("is_subtotal", False)
                                        op_data.append({
                                            "Categorie": f"**{cat_info['name']}**" if is_subtotal else cat_info["name"],
                                            "Bedrag": f"€ {value:,.0f}",
                                            "Type": "Subtotaal" if is_subtotal else "Invoer"
                                        })

                                if op_data:
                                    st.dataframe(pd.DataFrame(op_data), use_container_width=True, hide_index=True)

                                st.markdown("---")
                                st.markdown("#### Overige & Resultaat")

                                # Other and result section
                                other_data = []
                                other_cats = [
                                    "financieel_resultaat", "afschrijvingen", "totaal_overige_lasten",
                                    "resultaat_voor_belasting", "belastingen", "resultaat_na_belasting"
                                ]
                                for cat_key in other_cats:
                                    if cat_key in REPORT_CATEGORIES:
                                        cat_info = REPORT_CATEGORIES[cat_key]
                                        value = report_results.get(cat_key, 0)
                                        is_subtotal = cat_info.get("is_subtotal", False)
                                        other_data.append({
                                            "Categorie": f"**{cat_info['name']}**" if is_subtotal else cat_info["name"],
                                            "Bedrag": f"€ {value:,.0f}",
                                            "Type": "Subtotaal" if is_subtotal else "Invoer"
                                        })

                                if other_data:
                                    st.dataframe(pd.DataFrame(other_data), use_container_width=True, hide_index=True)

                                # Final summary
                                st.markdown("---")
                                final_result = report_results.get("resultaat_na_belasting", 0)
                                result_color = "green" if final_result >= 0 else "red"
                                st.markdown(f"### Resultaat na Belasting: :{result_color}[€ {final_result:,.0f}]")
                            else:
                                st.warning("Kon rapport niet berekenen. Controleer de mapping configuratie.")

                    # Export buttons
                    st.markdown("---")
                    st.markdown("### 📥 Exporteren")
                    exp_col1, exp_col2 = st.columns(2)

                    with exp_col1:
                        csv_data = export_forecast_to_csv(forecast, calculated)
                        st.download_button(
                            label="📄 Download CSV",
                            data=csv_data,
                            file_name=f"forecast_{forecast.get('name', 'export')}_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv"
                        )

                    with exp_col2:
                        try:
                            excel_data = export_forecast_to_excel(forecast, calculated)
                            if excel_data:
                                st.download_button(
                                    label="📊 Download Excel",
                                    data=excel_data,
                                    file_name=f"forecast_{forecast.get('name', 'export')}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                                )
                        except Exception as e:
                            st.caption("Excel export niet beschikbaar (openpyxl vereist)")

        # =====================================================================
        # SUBTAB 3: FORECAST VS ACTUAL COMPARISON
        # =====================================================================
        with forecast_subtabs[2]:
            st.subheader("📈 Forecast vs Actueel")

            if st.session_state.current_forecast is None:
                st.info("👈 Maak eerst een forecast aan in het 'Invoer / Scenario' tabblad")
            else:
                forecast = st.session_state.current_forecast
                calculated = calculate_forecast_metrics(forecast)
                periods = forecast.get("periods", [])

                st.caption("Vergelijk je forecast met actuele resultaten uit Odoo")

                # Fetch actual data button
                if st.button("🔄 Actuele Data Ophalen", type="primary"):
                    with st.spinner("Actuele data ophalen uit Odoo..."):
                        # Get configured account mapping from user's report structure
                        acct_mapping = st.session_state.get("forecast_account_mapping", DEFAULT_ACCOUNT_MAPPING)
                        revenue_patterns = acct_mapping["revenue"]["account_patterns"]
                        cogs_patterns = acct_mapping["cogs"]["account_patterns"]

                        actual_data = get_actual_data_for_comparison(
                            forecast.get("company_id"),
                            forecast.get("start_date"),
                            forecast.get("time_period_months", 12),
                            revenue_patterns=revenue_patterns,
                            cogs_patterns=cogs_patterns
                        )
                        if actual_data:
                            st.session_state.actual_data = actual_data
                            st.success("✅ Actuele data opgehaald!")
                        else:
                            st.warning("⚠️ Geen actuele data gevonden voor de geselecteerde periode")

                if "actual_data" in st.session_state and st.session_state.actual_data:
                    actual = st.session_state.actual_data
                    period_labels = [p["label"] for p in periods]

                    # Comparison Summary Cards
                    st.markdown("### 🎯 Vergelijking Kerncijfers")

                    comp_col1, comp_col2, comp_col3 = st.columns(3)

                    forecast_rev_total = calculated["total_revenue"]
                    actual_rev_total = sum(actual.get("revenue", []))
                    rev_variance = actual_rev_total - forecast_rev_total
                    rev_variance_pct = (rev_variance / forecast_rev_total * 100) if forecast_rev_total > 0 else 0

                    with comp_col1:
                        st.metric(
                            "📊 Omzet Forecast",
                            f"€{forecast_rev_total:,.0f}"
                        )
                        st.metric(
                            "📊 Omzet Actueel",
                            f"€{actual_rev_total:,.0f}",
                            delta=f"€{rev_variance:,.0f} ({rev_variance_pct:+.1f}%)",
                            delta_color="normal" if rev_variance >= 0 else "inverse"
                        )

                    # Calculate actual gross profit
                    actual_cogs_total = sum(actual.get("cogs", []))
                    actual_gp_total = actual_rev_total - actual_cogs_total
                    forecast_gp_total = calculated["total_gross_profit"]
                    gp_variance = actual_gp_total - forecast_gp_total

                    with comp_col2:
                        st.metric(
                            "📈 Brutowinst Forecast",
                            f"€{forecast_gp_total:,.0f}"
                        )
                        st.metric(
                            "📈 Brutowinst Actueel",
                            f"€{actual_gp_total:,.0f}",
                            delta=f"€{gp_variance:,.0f}",
                            delta_color="normal" if gp_variance >= 0 else "inverse"
                        )

                    # Calculate actual operating expenses
                    actual_opex_total = 0
                    for cat_vals in actual.get("operating_expenses", {}).values():
                        actual_opex_total += sum(cat_vals)
                    forecast_opex_total = sum(calculated["operating_expenses"])
                    opex_variance = actual_opex_total - forecast_opex_total

                    with comp_col3:
                        st.metric(
                            "📉 Op. Kosten Forecast",
                            f"€{forecast_opex_total:,.0f}"
                        )
                        st.metric(
                            "📉 Op. Kosten Actueel",
                            f"€{actual_opex_total:,.0f}",
                            delta=f"€{opex_variance:,.0f}",
                            delta_color="inverse" if opex_variance > 0 else "normal"  # Higher costs = bad
                        )

                    st.markdown("---")

                    # Revenue Comparison Chart
                    st.markdown("### 📊 Omzet: Forecast vs Actueel")

                    # Pad actual data if shorter than forecast periods
                    actual_revenue = actual.get("revenue", [])
                    while len(actual_revenue) < len(period_labels):
                        actual_revenue.append(0)

                    fig_compare = go.Figure()
                    fig_compare.add_trace(go.Bar(
                        x=period_labels,
                        y=calculated["revenue"],
                        name="Forecast",
                        marker_color="#1e3a5f",
                        opacity=0.7
                    ))
                    fig_compare.add_trace(go.Bar(
                        x=period_labels,
                        y=actual_revenue[:len(period_labels)],
                        name="Actueel",
                        marker_color="#2ecc71"
                    ))

                    fig_compare.update_layout(
                        barmode="group",
                        height=400,
                        yaxis=dict(title="Omzet (€)", tickformat=",.0f"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02)
                    )
                    st.plotly_chart(fig_compare, use_container_width=True)

                    # Variance Analysis Chart
                    st.markdown("### 📉 Variance Analyse")

                    variances = []
                    for i in range(min(len(calculated["revenue"]), len(actual_revenue))):
                        var = actual_revenue[i] - calculated["revenue"][i]
                        variances.append(var)

                    fig_variance = go.Figure()
                    fig_variance.add_trace(go.Bar(
                        x=period_labels[:len(variances)],
                        y=variances,
                        name="Variance",
                        marker_color=["#2ecc71" if v >= 0 else "#e74c3c" for v in variances],
                        text=[f"€{v:,.0f}" for v in variances],
                        textposition="outside"
                    ))

                    fig_variance.update_layout(
                        height=350,
                        yaxis=dict(title="Afwijking (€)", tickformat=",.0f"),
                        title="Afwijking Actueel vs Forecast (positief = beter dan forecast)"
                    )
                    st.plotly_chart(fig_variance, use_container_width=True)

                    # Detailed Variance Table
                    st.markdown("### 📋 Gedetailleerde Afwijkingen")

                    variance_data = []
                    for i, period in enumerate(period_labels):
                        if i < len(actual_revenue):
                            f_rev = calculated["revenue"][i]
                            a_rev = actual_revenue[i]
                            var_abs = a_rev - f_rev
                            var_pct = (var_abs / f_rev * 100) if f_rev > 0 else 0

                            # Determine status indicator
                            if var_pct >= 5:
                                status = "🟢"  # Good - above forecast
                            elif var_pct <= -10:
                                status = "🔴"  # Bad - significantly below
                            elif var_pct < 0:
                                status = "🟡"  # Warning - slightly below
                            else:
                                status = "🟢"  # OK

                            variance_data.append({
                                "Periode": period,
                                "Forecast": f"€{f_rev:,.0f}",
                                "Actueel": f"€{a_rev:,.0f}",
                                "Afwijking": f"€{var_abs:,.0f}",
                                "Afwijking %": f"{var_pct:+.1f}%",
                                "Status": status
                            })

                    if variance_data:
                        df_variance = pd.DataFrame(variance_data)
                        st.dataframe(df_variance, use_container_width=True, hide_index=True)

                else:
                    st.info("👆 Klik op 'Actuele Data Ophalen' om de vergelijking te starten")

        # =====================================================================
        # SUBTAB 4: SAVED FORECASTS
        # =====================================================================
        with forecast_subtabs[3]:
            st.subheader("💾 Opgeslagen Forecasts")

            saved_forecasts = list_saved_forecasts()

            if not saved_forecasts:
                st.info("📂 Nog geen forecasts opgeslagen. Maak een forecast aan en sla deze op.")
            else:
                st.caption(f"{len(saved_forecasts)} opgeslagen forecast(s) gevonden")

                for fc in saved_forecasts:
                    with st.container(border=True):
                        fc_col1, fc_col2, fc_col3, fc_col4 = st.columns([3, 2, 2, 1])

                        with fc_col1:
                            scenario_icon = SCENARIO_TEMPLATES.get(fc.get("scenario_type"), {}).get("icon", "📄")
                            st.markdown(f"### {scenario_icon} {fc['name']}")
                            company_name = COMPANIES.get(fc.get("company_id"), "Alle bedrijven")
                            st.caption(f"Bedrijf: {company_name} | Periode: {fc.get('time_period_months', 12)} maanden")

                        with fc_col2:
                            # Parse and format dates
                            try:
                                created = datetime.fromisoformat(fc.get("created_date", "")).strftime("%d-%m-%Y %H:%M")
                            except:
                                created = fc.get("created_date", "Onbekend")
                            st.caption(f"Aangemaakt: {created}")

                        with fc_col3:
                            try:
                                modified = datetime.fromisoformat(fc.get("last_modified", "")).strftime("%d-%m-%Y %H:%M")
                            except:
                                modified = fc.get("last_modified", "Onbekend")
                            st.caption(f"Gewijzigd: {modified}")

                        with fc_col4:
                            btn_col1, btn_col2 = st.columns(2)
                            with btn_col1:
                                if st.button("📂", key=f"load_{fc['filename']}", help="Laden"):
                                    loaded, error = load_forecast(fc['filename'])
                                    if loaded:
                                        st.session_state.current_forecast = loaded
                                        st.success(f"✅ {fc['name']} geladen!")
                                        st.rerun()
                                    else:
                                        st.error(f"❌ {error}")
                            with btn_col2:
                                if st.button("🗑️", key=f"delete_{fc['filename']}", help="Verwijderen"):
                                    success, msg = delete_forecast(fc['filename'])
                                    if success:
                                        st.success("Forecast verwijderd")
                                        st.rerun()
                                    else:
                                        st.error(msg)


    # =========================================================================
    # TAB 12: BUDGET 2026
    # =========================================================================
    with tabs[11]:
        st.header("🎯 Budget & Forecast 2026")
        st.caption("Gebaseerd op 2025 actuals met aanpasbare groeiparameters")
        
        # =====================================================================
        # 2025 ACTUALS DATA (hard-coded voor snelheid, kan later live worden)
        # =====================================================================
        ACTUALS_2025 = {
            "Omzet": {
                "Jan": 784627, "Feb": 648898, "Mrt": 777040, "Apr": 752291,
                "Mei": 824063, "Jun": 895398, "Jul": 742339, "Aug": 714975,
                "Sep": 957451, "Okt": 1018631, "Nov": 1253668, "Dec": 822146,
                "Totaal": 10191527
            },
            "Kostprijs Verkopen": {
                "Jan": 464000, "Feb": 383783, "Mrt": 459517, "Apr": 444879,
                "Mei": 487312, "Jun": 529495, "Jul": 438991, "Aug": 422808,
                "Sep": 566176, "Okt": 602349, "Nov": 741294, "Dec": 486281,
                "Totaal": 6026886
            },
            "Personeelskosten": {
                "Jan": 165940, "Feb": 165940, "Mrt": 165940, "Apr": 165940,
                "Mei": 165940, "Jun": 165940, "Jul": 165940, "Aug": 165940,
                "Sep": 165940, "Okt": 165940, "Nov": 165940, "Dec": 165940,
                "Totaal": 1991282
            },
            "Huisvestingskosten": {
                "Jan": 21961, "Feb": 21961, "Mrt": 21961, "Apr": 21961,
                "Mei": 21961, "Jun": 21961, "Jul": 21961, "Aug": 21961,
                "Sep": 21961, "Okt": 21961, "Nov": 21961, "Dec": 21961,
                "Totaal": 263526
            },
            "Kantoorkosten": {
                "Jan": 26135, "Feb": 26135, "Mrt": 26135, "Apr": 26135,
                "Mei": 26135, "Jun": 26135, "Jul": 26135, "Aug": 26135,
                "Sep": 26135, "Okt": 26135, "Nov": 26135, "Dec": 26135,
                "Totaal": 313625
            },
            "Verkoop & Marketing": {
                "Jan": 97715, "Feb": 97715, "Mrt": 97715, "Apr": 97715,
                "Mei": 97715, "Jun": 97715, "Jul": 97715, "Aug": 97715,
                "Sep": 97715, "Okt": 97715, "Nov": 97715, "Dec": 97715,
                "Totaal": 1172575
            },
            "Overige Kosten": {
                "Jan": 34018, "Feb": 34018, "Mrt": 34018, "Apr": 34018,
                "Mei": 34018, "Jun": 34018, "Jul": 34018, "Aug": 34018,
                "Sep": 34018, "Okt": 34018, "Nov": 34018, "Dec": 34018,
                "Totaal": 408210
            }
        }
        
        MAANDEN = ["Jan", "Feb", "Mrt", "Apr", "Mei", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dec"]
        
        # =====================================================================
        # SIDEBAR: BUDGET PARAMETERS
        # =====================================================================
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 🎯 Budget Parameters 2026")
        
        # Initialize session state for growth rates
        if "budget_growth_rates" not in st.session_state:
            st.session_state.budget_growth_rates = {
                "Omzet": 5.0,
                "Kostprijs Verkopen": 5.0,
                "Personeelskosten": 3.0,
                "Huisvestingskosten": 2.0,
                "Kantoorkosten": 2.0,
                "Verkoop & Marketing": 5.0,
                "Overige Kosten": 1.0
            }
        
        growth_rates = {}
        for group in ACTUALS_2025.keys():
            default = st.session_state.budget_growth_rates.get(group, 5.0)
            growth_rates[group] = st.sidebar.slider(
                f"{group}",
                min_value=-20.0,
                max_value=30.0,
                value=default,
                step=0.5,
                format="%.1f%%",
                key=f"budget_growth_{group}"
            )
        
        # Update session state
        st.session_state.budget_growth_rates = growth_rates
        
        # Reset button
        if st.sidebar.button("🔄 Reset naar standaard"):
            st.session_state.budget_growth_rates = {
                "Omzet": 5.0, "Kostprijs Verkopen": 5.0, "Personeelskosten": 3.0,
                "Huisvestingskosten": 2.0, "Kantoorkosten": 2.0, 
                "Verkoop & Marketing": 5.0, "Overige Kosten": 1.0
            }
            st.rerun()
        
        # =====================================================================
        # BEREKEN FORECAST
        # =====================================================================
        forecast_2026 = {}
        for group, actuals in ACTUALS_2025.items():
            growth = 1 + growth_rates[group] / 100
            forecast_2026[group] = {
                month: int(actuals[month] * growth) for month in MAANDEN
            }
            forecast_2026[group]["Totaal"] = sum(forecast_2026[group][m] for m in MAANDEN)
        
        # =====================================================================
        # KPI SAMENVATTING
        # =====================================================================
        col1, col2, col3, col4 = st.columns(4)
        
        # Bereken totalen
        omzet_2025 = ACTUALS_2025["Omzet"]["Totaal"]
        omzet_2026 = forecast_2026["Omzet"]["Totaal"]
        
        kosten_2025 = sum(ACTUALS_2025[g]["Totaal"] for g in ACTUALS_2025 if g != "Omzet")
        kosten_2026 = sum(forecast_2026[g]["Totaal"] for g in forecast_2026 if g != "Omzet")
        
        bruto_marge_2025 = omzet_2025 - ACTUALS_2025["Kostprijs Verkopen"]["Totaal"]
        bruto_marge_2026 = omzet_2026 - forecast_2026["Kostprijs Verkopen"]["Totaal"]
        
        netto_2025 = omzet_2025 - kosten_2025
        netto_2026 = omzet_2026 - kosten_2026
        
        with col1:
            st.metric(
                "💰 Omzet Forecast 2026",
                f"€{omzet_2026:,.0f}",
                delta=f"{(omzet_2026/omzet_2025-1)*100:+.1f}% vs 2025"
            )
        
        with col2:
            st.metric(
                "📦 Bruto Marge 2026",
                f"€{bruto_marge_2026:,.0f}",
                delta=f"{bruto_marge_2026/omzet_2026*100:.1f}%"
            )
        
        with col3:
            st.metric(
                "📉 Kosten Forecast 2026",
                f"€{kosten_2026:,.0f}",
                delta=f"{(kosten_2026/kosten_2025-1)*100:+.1f}%"
            )
        
        with col4:
            st.metric(
                "📊 Netto Resultaat 2026",
                f"€{netto_2026:,.0f}",
                delta=f"€{netto_2026-netto_2025:+,.0f} vs 2025"
            )
        
        # =====================================================================
        # SUBTABS
        # =====================================================================
        budget_tabs = st.tabs(["📊 Overzicht", "📈 Omzet Analyse", "📉 Kosten Analyse", "📋 Detail Tabel", "🎯 Variantie & Scenario"])
        
        # ----- SUBTAB 1: OVERZICHT -----
        with budget_tabs[0]:
            st.subheader("Omzet: 2025 Actual vs 2026 Forecast")
            
            # Maak vergelijking chart
            fig = go.Figure()
            
            fig.add_trace(go.Bar(
                name="2025 Actual",
                x=MAANDEN,
                y=[ACTUALS_2025["Omzet"][m] for m in MAANDEN],
                marker_color="#3498db"
            ))
            
            fig.add_trace(go.Bar(
                name="2026 Forecast",
                x=MAANDEN,
                y=[forecast_2026["Omzet"][m] for m in MAANDEN],
                marker_color="#e74c3c"
            ))
            
            fig.update_layout(
                barmode="group",
                yaxis_tickformat="€,.0s",
                height=400,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0.5, xanchor="center")
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Seizoenspatroon analyse
            st.subheader("🗓️ Seizoenspatroon")
            
            seizoen_data = []
            for m in MAANDEN:
                pct_2025 = ACTUALS_2025["Omzet"][m] / omzet_2025 * 100
                pct_2026 = forecast_2026["Omzet"][m] / omzet_2026 * 100
                seizoen_data.append({
                    "Maand": m,
                    "% 2025": pct_2025,
                    "% 2026": pct_2026
                })
            
            df_seizoen = pd.DataFrame(seizoen_data)
            
            fig_seizoen = px.line(
                df_seizoen, x="Maand", y=["% 2025", "% 2026"],
                markers=True,
                title="Omzetverdeling per maand (%)"
            )
            fig_seizoen.update_layout(yaxis_title="% van Jaaromzet", height=300)
            st.plotly_chart(fig_seizoen, use_container_width=True)
        
        # ----- SUBTAB 2: OMZET ANALYSE -----
        with budget_tabs[1]:
            st.subheader("📈 Omzet Forecast Analyse")
            
            # Cumulatieve omzet
            cum_2025 = []
            cum_2026 = []
            running_2025 = 0
            running_2026 = 0
            
            for m in MAANDEN:
                running_2025 += ACTUALS_2025["Omzet"][m]
                running_2026 += forecast_2026["Omzet"][m]
                cum_2025.append(running_2025)
                cum_2026.append(running_2026)
            
            fig_cum = go.Figure()
            fig_cum.add_trace(go.Scatter(
                x=MAANDEN, y=cum_2025,
                mode="lines+markers",
                name="2025 Actual (Cum.)",
                line=dict(color="#3498db", width=3)
            ))
            fig_cum.add_trace(go.Scatter(
                x=MAANDEN, y=cum_2026,
                mode="lines+markers",
                name="2026 Forecast (Cum.)",
                line=dict(color="#e74c3c", width=3, dash="dash")
            ))
            fig_cum.update_layout(title="Cumulatieve Omzet", yaxis_tickformat="€,.0s", height=400)
            st.plotly_chart(fig_cum, use_container_width=True)
            
            # Beste/slechtste maanden
            col1, col2 = st.columns(2)
            sorted_months = sorted(MAANDEN, key=lambda m: ACTUALS_2025["Omzet"][m], reverse=True)
            
            with col1:
                st.markdown("**🏆 Beste maanden (2025)**")
                for m in sorted_months[:3]:
                    st.write(f"• {m}: €{ACTUALS_2025['Omzet'][m]:,.0f}")
            
            with col2:
                st.markdown("**⚠️ Zwakste maanden (2025)**")
                for m in sorted_months[-3:]:
                    st.write(f"• {m}: €{ACTUALS_2025['Omzet'][m]:,.0f}")
        
        # ----- SUBTAB 3: KOSTEN ANALYSE -----
        with budget_tabs[2]:
            st.subheader("📉 Kosten Forecast per Groep")
            
            # Kosten breakdown
            kosten_groepen = [g for g in ACTUALS_2025.keys() if g != "Omzet"]
            
            kosten_2025_list = [ACTUALS_2025[g]["Totaal"] for g in kosten_groepen]
            kosten_2026_list = [forecast_2026[g]["Totaal"] for g in kosten_groepen]
            groei_pct = [(forecast_2026[g]["Totaal"] / ACTUALS_2025[g]["Totaal"] - 1) * 100 for g in kosten_groepen]
            
            fig_kosten = go.Figure()
            
            fig_kosten.add_trace(go.Bar(
                name="2025 Actual",
                y=kosten_groepen,
                x=kosten_2025_list,
                orientation="h",
                marker_color="#3498db",
                text=[f"€{v/1e6:.2f}M" for v in kosten_2025_list],
                textposition="auto"
            ))
            
            fig_kosten.add_trace(go.Bar(
                name="2026 Forecast",
                y=kosten_groepen,
                x=kosten_2026_list,
                orientation="h",
                marker_color="#e74c3c",
                text=[f"€{v/1e6:.2f}M ({g:+.1f}%)" for v, g in zip(kosten_2026_list, groei_pct)],
                textposition="auto"
            ))
            
            fig_kosten.update_layout(barmode="group", xaxis_tickformat="€,.0s", height=400)
            st.plotly_chart(fig_kosten, use_container_width=True)
            
            # Kosten als % van omzet
            st.subheader("Kosten als % van Omzet")
            
            kosten_pct_data = []
            for g in kosten_groepen:
                kosten_pct_data.append({
                    "Groep": g,
                    "2025 %": ACTUALS_2025[g]["Totaal"] / omzet_2025 * 100,
                    "2026 %": forecast_2026[g]["Totaal"] / omzet_2026 * 100
                })
            
            df_kosten_pct = pd.DataFrame(kosten_pct_data)
            st.dataframe(
                df_kosten_pct.style.format({"2025 %": "{:.1f}%", "2026 %": "{:.1f}%"}),
                use_container_width=True,
                hide_index=True
            )
        
        # ----- SUBTAB 4: DETAIL TABEL -----
        with budget_tabs[3]:
            st.subheader("📋 Maandelijkse Detail")
            
            # Selecteer groep
            selected_group = st.selectbox(
                "Selecteer rekeninggroep",
                list(ACTUALS_2025.keys()),
                key="budget_detail_group"
            )
            
            # Maak detail tabel
            detail_data = []
            for m in MAANDEN:
                actual_2025 = ACTUALS_2025[selected_group][m]
                forecast = forecast_2026[selected_group][m]
                verschil = forecast - actual_2025
                pct_change = (forecast / actual_2025 - 1) * 100 if actual_2025 else 0
                
                detail_data.append({
                    "Maand": m,
                    "2025 Actual": actual_2025,
                    "2026 Forecast": forecast,
                    "Verschil": verschil,
                    "% Groei": pct_change
                })
            
            # Voeg totaal toe
            detail_data.append({
                "Maand": "TOTAAL",
                "2025 Actual": ACTUALS_2025[selected_group]["Totaal"],
                "2026 Forecast": forecast_2026[selected_group]["Totaal"],
                "Verschil": forecast_2026[selected_group]["Totaal"] - ACTUALS_2025[selected_group]["Totaal"],
                "% Groei": (forecast_2026[selected_group]["Totaal"] / ACTUALS_2025[selected_group]["Totaal"] - 1) * 100
            })
            
            df_detail = pd.DataFrame(detail_data)
            
            st.dataframe(
                df_detail.style.format({
                    "2025 Actual": "€{:,.0f}",
                    "2026 Forecast": "€{:,.0f}",
                    "Verschil": "€{:+,.0f}",
                    "% Groei": "{:+.1f}%"
                }),
                use_container_width=True,
                hide_index=True
            )
            
            # Download opties
            col_csv, col_excel = st.columns(2)
            
            with col_csv:
                csv = df_detail.to_csv(index=False)
                st.download_button(
                    "📥 Download als CSV",
                    csv,
                    f"budget_forecast_{selected_group.replace(' ', '_')}.csv",
                    "text/csv",
                    key="budget_download_csv"
                )
            
            with col_excel:
                # Excel export met alle data
                try:
                    from io import BytesIO
                    
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        # Sheet 1: Samenvatting KPIs
                        summary_export = pd.DataFrame({
                            "Metric": ["Omzet", "Kostprijs Verkopen", "Bruto Marge", "Bruto Marge %", 
                                      "Personeelskosten", "Huisvestingskosten", "Kantoorkosten",
                                      "Verkoop & Marketing", "Overige Kosten", "Totale Kosten", "Netto Resultaat", "Netto Marge %"],
                            "2025 Actual": [
                                ACTUALS_2025["Omzet"]["Totaal"],
                                ACTUALS_2025["Kostprijs Verkopen"]["Totaal"],
                                ACTUALS_2025["Omzet"]["Totaal"] - ACTUALS_2025["Kostprijs Verkopen"]["Totaal"],
                                (ACTUALS_2025["Omzet"]["Totaal"] - ACTUALS_2025["Kostprijs Verkopen"]["Totaal"]) / ACTUALS_2025["Omzet"]["Totaal"] * 100,
                                ACTUALS_2025["Personeelskosten"]["Totaal"],
                                ACTUALS_2025["Huisvestingskosten"]["Totaal"],
                                ACTUALS_2025["Kantoorkosten"]["Totaal"],
                                ACTUALS_2025["Verkoop & Marketing"]["Totaal"],
                                ACTUALS_2025["Overige Kosten"]["Totaal"],
                                sum(ACTUALS_2025[g]["Totaal"] for g in ACTUALS_2025 if g != "Omzet"),
                                ACTUALS_2025["Omzet"]["Totaal"] - sum(ACTUALS_2025[g]["Totaal"] for g in ACTUALS_2025 if g != "Omzet"),
                                (ACTUALS_2025["Omzet"]["Totaal"] - sum(ACTUALS_2025[g]["Totaal"] for g in ACTUALS_2025 if g != "Omzet")) / ACTUALS_2025["Omzet"]["Totaal"] * 100
                            ],
                            "2026 Forecast": [
                                forecast_2026["Omzet"]["Totaal"],
                                forecast_2026["Kostprijs Verkopen"]["Totaal"],
                                forecast_2026["Omzet"]["Totaal"] - forecast_2026["Kostprijs Verkopen"]["Totaal"],
                                (forecast_2026["Omzet"]["Totaal"] - forecast_2026["Kostprijs Verkopen"]["Totaal"]) / forecast_2026["Omzet"]["Totaal"] * 100,
                                forecast_2026["Personeelskosten"]["Totaal"],
                                forecast_2026["Huisvestingskosten"]["Totaal"],
                                forecast_2026["Kantoorkosten"]["Totaal"],
                                forecast_2026["Verkoop & Marketing"]["Totaal"],
                                forecast_2026["Overige Kosten"]["Totaal"],
                                sum(forecast_2026[g]["Totaal"] for g in forecast_2026 if g != "Omzet"),
                                forecast_2026["Omzet"]["Totaal"] - sum(forecast_2026[g]["Totaal"] for g in forecast_2026 if g != "Omzet"),
                                (forecast_2026["Omzet"]["Totaal"] - sum(forecast_2026[g]["Totaal"] for g in forecast_2026 if g != "Omzet")) / forecast_2026["Omzet"]["Totaal"] * 100
                            ],
                            "Verschil": [
                                forecast_2026["Omzet"]["Totaal"] - ACTUALS_2025["Omzet"]["Totaal"],
                                forecast_2026["Kostprijs Verkopen"]["Totaal"] - ACTUALS_2025["Kostprijs Verkopen"]["Totaal"],
                                (forecast_2026["Omzet"]["Totaal"] - forecast_2026["Kostprijs Verkopen"]["Totaal"]) - (ACTUALS_2025["Omzet"]["Totaal"] - ACTUALS_2025["Kostprijs Verkopen"]["Totaal"]),
                                "",
                                forecast_2026["Personeelskosten"]["Totaal"] - ACTUALS_2025["Personeelskosten"]["Totaal"],
                                forecast_2026["Huisvestingskosten"]["Totaal"] - ACTUALS_2025["Huisvestingskosten"]["Totaal"],
                                forecast_2026["Kantoorkosten"]["Totaal"] - ACTUALS_2025["Kantoorkosten"]["Totaal"],
                                forecast_2026["Verkoop & Marketing"]["Totaal"] - ACTUALS_2025["Verkoop & Marketing"]["Totaal"],
                                forecast_2026["Overige Kosten"]["Totaal"] - ACTUALS_2025["Overige Kosten"]["Totaal"],
                                sum(forecast_2026[g]["Totaal"] for g in forecast_2026 if g != "Omzet") - sum(ACTUALS_2025[g]["Totaal"] for g in ACTUALS_2025 if g != "Omzet"),
                                (forecast_2026["Omzet"]["Totaal"] - sum(forecast_2026[g]["Totaal"] for g in forecast_2026 if g != "Omzet")) - (ACTUALS_2025["Omzet"]["Totaal"] - sum(ACTUALS_2025[g]["Totaal"] for g in ACTUALS_2025 if g != "Omzet")),
                                ""
                            ],
                            "Groei %": [
                                (forecast_2026["Omzet"]["Totaal"] / ACTUALS_2025["Omzet"]["Totaal"] - 1) * 100,
                                (forecast_2026["Kostprijs Verkopen"]["Totaal"] / ACTUALS_2025["Kostprijs Verkopen"]["Totaal"] - 1) * 100,
                                ((forecast_2026["Omzet"]["Totaal"] - forecast_2026["Kostprijs Verkopen"]["Totaal"]) / (ACTUALS_2025["Omzet"]["Totaal"] - ACTUALS_2025["Kostprijs Verkopen"]["Totaal"]) - 1) * 100,
                                "",
                                (forecast_2026["Personeelskosten"]["Totaal"] / ACTUALS_2025["Personeelskosten"]["Totaal"] - 1) * 100,
                                (forecast_2026["Huisvestingskosten"]["Totaal"] / ACTUALS_2025["Huisvestingskosten"]["Totaal"] - 1) * 100,
                                (forecast_2026["Kantoorkosten"]["Totaal"] / ACTUALS_2025["Kantoorkosten"]["Totaal"] - 1) * 100,
                                (forecast_2026["Verkoop & Marketing"]["Totaal"] / ACTUALS_2025["Verkoop & Marketing"]["Totaal"] - 1) * 100,
                                (forecast_2026["Overige Kosten"]["Totaal"] / ACTUALS_2025["Overige Kosten"]["Totaal"] - 1) * 100,
                                (sum(forecast_2026[g]["Totaal"] for g in forecast_2026 if g != "Omzet") / sum(ACTUALS_2025[g]["Totaal"] for g in ACTUALS_2025 if g != "Omzet") - 1) * 100,
                                "",
                                ""
                            ]
                        })
                        summary_export.to_excel(writer, sheet_name="Samenvatting", index=False)
                        
                        # Sheet 2: Maanddetail per groep
                        all_monthly_data = []
                        for group in ACTUALS_2025.keys():
                            for m in MAANDEN:
                                all_monthly_data.append({
                                    "Groep": group,
                                    "Maand": m,
                                    "2025 Actual": ACTUALS_2025[group][m],
                                    "2026 Forecast": forecast_2026[group][m],
                                    "Verschil": forecast_2026[group][m] - ACTUALS_2025[group][m],
                                    "Groei %": (forecast_2026[group][m] / ACTUALS_2025[group][m] - 1) * 100 if ACTUALS_2025[group][m] else 0
                                })
                        df_monthly = pd.DataFrame(all_monthly_data)
                        df_monthly.to_excel(writer, sheet_name="Maanddetail", index=False)
                        
                        # Sheet 3: Parameters
                        params_data = []
                        for group, pct in growth_rates.items():
                            params_data.append({
                                "Rekeninggroep": group,
                                "Groei %": pct,
                                "2025 Totaal": ACTUALS_2025[group]["Totaal"],
                                "2026 Forecast": forecast_2026[group]["Totaal"]
                            })
                        df_params = pd.DataFrame(params_data)
                        df_params.to_excel(writer, sheet_name="Parameters", index=False)
                        
                        # Sheet 4: Scenario's
                        omzet_fc = forecast_2026["Omzet"]["Totaal"]
                        kosten_fc = sum(forecast_2026[g]["Totaal"] for g in forecast_2026 if g != "Omzet")
                        netto_fc = omzet_fc - kosten_fc
                        
                        scenarios = pd.DataFrame({
                            "Scenario": ["Pessimistisch", "Basis", "Optimistisch"],
                            "Omzet Aanpassing": ["-5%", "0%", "+10%"],
                            "Kosten Aanpassing": ["+2%", "0%", "+3%"],
                            "Omzet": [omzet_fc * 0.95, omzet_fc, omzet_fc * 1.10],
                            "Kosten": [kosten_fc * 1.02, kosten_fc, kosten_fc * 1.03],
                            "Netto Resultaat": [omzet_fc * 0.95 - kosten_fc * 1.02, netto_fc, omzet_fc * 1.10 - kosten_fc * 1.03]
                        })
                        scenarios.to_excel(writer, sheet_name="Scenarios", index=False)
                        
                        # Sheet 5: Geselecteerde groep detail
                        df_detail.to_excel(writer, sheet_name=f"Detail {selected_group[:20]}", index=False)
                    
                    excel_data = output.getvalue()
                    
                    st.download_button(
                        "📊 Download Excel (alle data)",
                        excel_data,
                        f"LAB_Budget_Forecast_2026_{datetime.now().strftime('%Y%m%d')}.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="budget_download_excel"
                    )
                except ImportError:
                    st.warning("openpyxl niet geïnstalleerd - Excel export niet beschikbaar")
                except Exception as e:
                    st.error(f"Excel export fout: {e}")
        
        # ----- SUBTAB 5: VARIANTIE & SCENARIO -----
        with budget_tabs[4]:
            st.subheader("🎯 Variantie Analyse & Scenario Planning")
            
            # Variantie sectie
            st.markdown("### 📊 Variantie: Forecast vs Actual 2026")
            
            current_year = datetime.now().year
            current_month = datetime.now().month
            
            if current_year >= 2026:
                st.info("💡 Zodra 2026 data beschikbaar is, wordt hier automatisch de variantie getoond.")
                
                # Poging om 2026 actuals op te halen
                try:
                    with st.spinner("2026 actuals ophalen uit Odoo..."):
                        revenue_2026_api = get_revenue_aggregated(2026, None)
                        
                        if revenue_2026_api and sum(r.get("balance", 0) for r in revenue_2026_api) != 0:
                            st.success("✅ 2026 omzetdata gevonden!")
                            
                            # Toon variantie tabel
                            variance_data = []
                            actuals_by_month = {}
                            
                            for r in revenue_2026_api:
                                month_str = r.get("date:month", "")
                                balance = -r.get("balance", 0)
                                # Parse maandnaam (verwacht format "januari 2026" of vergelijkbaar)
                                if month_str:
                                    month_key = month_str.split()[0][:3].capitalize()
                                    actuals_by_month[month_key] = actuals_by_month.get(month_key, 0) + balance
                            
                            for m in MAANDEN[:current_month]:
                                fc = forecast_2026["Omzet"][m]
                                act = actuals_by_month.get(m, 0)
                                if act > 0:
                                    var = act - fc
                                    pct = (act / fc - 1) * 100 if fc else 0
                                    status = "🟢" if abs(pct) <= 5 else ("🟡" if abs(pct) <= 10 else "🔴")
                                    variance_data.append({
                                        "Maand": m,
                                        "Forecast": fc,
                                        "Actual": act,
                                        "Variantie": var,
                                        "% Var": pct,
                                        "Status": status
                                    })
                            
                            if variance_data:
                                df_var = pd.DataFrame(variance_data)
                                st.dataframe(
                                    df_var.style.format({
                                        "Forecast": "€{:,.0f}",
                                        "Actual": "€{:,.0f}",
                                        "Variantie": "€{:+,.0f}",
                                        "% Var": "{:+.1f}%"
                                    }),
                                    use_container_width=True,
                                    hide_index=True
                                )
                        else:
                            st.warning("Nog geen 2026 omzet data in Odoo.")
                except Exception as e:
                    st.warning(f"Kon 2026 data niet ophalen: {e}")
            else:
                st.info(f"📅 Variantie analyse wordt beschikbaar vanaf januari 2026.")
            
            # Scenario analyse sectie
            st.markdown("---")
            st.markdown("### 🔮 Scenario Analyse")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown("**📉 Pessimistisch**")
                st.caption("Omzet -5%, Kosten +2%")
                omzet_pess = omzet_2026 * 0.95
                kosten_pess = kosten_2026 * 1.02
                netto_pess = omzet_pess - kosten_pess
                st.metric("Omzet", f"€{omzet_pess:,.0f}")
                st.metric("Netto", f"€{netto_pess:,.0f}", delta=f"€{netto_pess-netto_2026:+,.0f}")
            
            with col2:
                st.markdown("**📊 Basis Forecast**")
                st.caption("Huidige parameters")
                st.metric("Omzet", f"€{omzet_2026:,.0f}")
                st.metric("Netto", f"€{netto_2026:,.0f}")
            
            with col3:
                st.markdown("**📈 Optimistisch**")
                st.caption("Omzet +10%, Kosten +3%")
                omzet_opt = omzet_2026 * 1.10
                kosten_opt = kosten_2026 * 1.03
                netto_opt = omzet_opt - kosten_opt
                st.metric("Omzet", f"€{omzet_opt:,.0f}")
                st.metric("Netto", f"€{netto_opt:,.0f}", delta=f"€{netto_opt-netto_2026:+,.0f}")
            
            # Samenvatting tabel
            st.markdown("---")
            st.markdown("### 📋 Forecast Samenvatting")
            
            summary_data = {
                "Metric": ["Omzet", "Bruto Marge", "Bruto Marge %", "Operationele Kosten", "Netto Resultaat", "Netto Marge %"],
                "2025 Actual": [
                    f"€{omzet_2025:,.0f}",
                    f"€{bruto_marge_2025:,.0f}",
                    f"{bruto_marge_2025/omzet_2025*100:.1f}%",
                    f"€{kosten_2025 - ACTUALS_2025['Kostprijs Verkopen']['Totaal']:,.0f}",
                    f"€{netto_2025:,.0f}",
                    f"{netto_2025/omzet_2025*100:.1f}%"
                ],
                "2026 Forecast": [
                    f"€{omzet_2026:,.0f}",
                    f"€{bruto_marge_2026:,.0f}",
                    f"{bruto_marge_2026/omzet_2026*100:.1f}%",
                    f"€{kosten_2026 - forecast_2026['Kostprijs Verkopen']['Totaal']:,.0f}",
                    f"€{netto_2026:,.0f}",
                    f"{netto_2026/omzet_2026*100:.1f}%"
                ],
                "Verschil": [
                    f"€{omzet_2026-omzet_2025:+,.0f}",
                    f"€{bruto_marge_2026-bruto_marge_2025:+,.0f}",
                    f"{(bruto_marge_2026/omzet_2026 - bruto_marge_2025/omzet_2025)*100:+.1f}pp",
                    f"€{(kosten_2026-forecast_2026['Kostprijs Verkopen']['Totaal'])-(kosten_2025-ACTUALS_2025['Kostprijs Verkopen']['Totaal']):+,.0f}",
                    f"€{netto_2026-netto_2025:+,.0f}",
                    f"{(netto_2026/omzet_2026 - netto_2025/omzet_2025)*100:+.1f}pp"
                ]
            }
            
            df_summary = pd.DataFrame(summary_data)
            st.dataframe(df_summary, use_container_width=True, hide_index=True)



if __name__ == "__main__":
    main()
