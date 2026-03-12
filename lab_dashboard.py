"""
LAB Groep Financial Dashboard v19
=================================
Wijzigingen t.o.v. v18:
- 🧮 Nieuwe rapportagepagina toegevoegd
  * Rekeningmapping op geaggregeerd W&V niveau (incl. bulk)
  * Budget importtemplate + upload op rapportregelniveau per bedrijf
  * Maandelijkse actual vs budget variantieanalyse op hetzelfde niveau
  * Aparte balansmapping en balansrapport in Activa/Passiva structuur

Wijzigingen t.o.v. v17:
- 🧹 Navigatie opgeschoond
  * Cashflow prognose feature verwijderd
  * Maandafsluiting feature verwijderd
- 🐛 Stabiliteit: voorkomen van fouten door uitgefaseerde rapport-tabs
- ✨ UX verbeterd
  * API-instellingen samengevoegd in inklapbaar paneel
  * Compacte filterbalk met duidelijke actieve selectie
  * Rustigere, consistente navigatiestijl

Wijzigingen t.o.v. v16:
- 📊 Uitgebreide variantie analyse in Budget 2026 tab
  * Variantie per rubriek (Omzet, Kostprijs, Personeelskosten, etc.)
  * Maandelijkse breakdown per categorie met totaalrijen
  * Samenvatting tabel met alle rubrieken + netto resultaat
  * Session state caching voor 2026 actuals (voorkomt herhaald laden)
  * Handmatige refresh knop voor 2026 actuals
- ⚡ Performance verbetering
  * Budget parameters in st.form (sliders triggeren geen full rerun meer)
  * 2026 actuals gecached in session_state
- 🐛 Fix: Nederlandse maandnamen correct gemapt (maart -> Mrt)

Wijzigingen t.o.v. v15:
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
  - Grouped bar chart: huidig jaar vs vorig jaar per weeknummer
  - YoY statistieken (totaal, verschil, percentage)
- 📊 Categorie Trend subtab in Producten tab
  - Productcategorie filter (selectbox)
  - Week-op-week omzet grafiek per geselecteerde categorie
  - Cumulatieve omzet grafiek per geselecteerde categorie
  - Ondersteuning voor zowel factuur- als POS-data (Conceptstore)

Wijzigingen t.o.v. v13:
- 🔮 Financial Forecast module toegevoegd
  - Handmatige forecast invoer met omzet, COGS, en operationele kosten
  - 3 scenario templates: Conservatief, Gematigd, Agressief
  - Aanpasbare aannames (klantacquisitie, churn, inflatie, seizoensfactoren)
  - Eenmalige events (inkomsten/uitgaven) toevoegen
  - Forecast resultaten met grafieken en KPIs
  - Vergelijking met actuele data uit Odoo
  - Opslaan en laden van forecasts (JSON)
  - Export naar CSV en Excel
  - CASHFLOW_HOOK: Voorbereid voor integratie met cashflow prognose

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
import re

# =============================================================================
# CONFIGURATIE
# =============================================================================

st.set_page_config(
    page_title="LAB Groep Dashboard",
    page_icon=":material/finance:",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Odoo configuratie
ODOO_URL = "https://lab.odoo.works/jsonrpc"
ODOO_DB = "lab.odoo.works"
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

# Nederlandse maandnamen naar korte afkortingen (voor Odoo read_group output)
DUTCH_MONTH_MAP = {
    "januari": "Jan", "februari": "Feb", "maart": "Mrt",
    "april": "Apr", "mei": "Mei", "juni": "Jun",
    "juli": "Jul", "augustus": "Aug", "september": "Sep",
    "oktober": "Okt", "november": "Nov", "december": "Dec"
}

# Mapping van budget categorieën naar rekeningcode bereiken
BUDGET_CATEGORY_ACCOUNTS = {
    "Omzet": [("800000", "900000")],
    "Kostprijs Verkopen": [("700000", "800000")],
    "Personeelskosten": [("400000", "410000")],
    "Huisvestingskosten": [("410000", "420000")],
    "Kantoorkosten": [("430000", "440000")],
    "Verkoop & Marketing": [("440000", "450000")],
    "Overige Kosten": [("420000", "430000"), ("450000", "500000"), ("600000", "700000")]
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
- Balans en liquiditeit

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
def get_2026_actuals_by_category(company_id=None):
    """Haal 2026 actuals op per budgetcategorie en maand voor variantie analyse.

    Returns dict: {category_name: {month_abbrev: amount, ...}, ...}
    Bedragen zijn positief voor zowel omzet als kosten.
    """
    results = {}

    for category, ranges in BUDGET_CATEGORY_ACCOUNTS.items():
        monthly = {}
        for code_from, code_to in ranges:
            domain = [
                ("account_id.code", ">=", code_from),
                ("account_id.code", "<", code_to),
                ("date", ">=", "2026-01-01"),
                ("date", "<=", "2026-12-31"),
                ("parent_state", "=", "posted")
            ]
            if company_id:
                domain.append(("company_id", "=", company_id))

            data = odoo_read_group("account.move.line", domain, ["balance:sum"], ["date:month"])
            for r in data:
                month_str = r.get("date:month", "")
                balance = r.get("balance", 0)
                # Omzet is negatief in Odoo, kosten positief
                if category == "Omzet":
                    balance = -balance
                if month_str:
                    month_word = month_str.split()[0].lower()
                    month_key = DUTCH_MONTH_MAP.get(month_word, month_str.split()[0][:3].capitalize())
                    monthly[month_key] = monthly.get(month_key, 0) + balance
        results[category] = monthly

    return results

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

# =============================================================================
# ANALYTISCHE PROJECTFUNCTIES
# =============================================================================

@st.cache_data(ttl=3600)
def get_analytic_plans():
    """Haal analytische plannen op uit Odoo (account.analytic.plan)."""
    return odoo_call(
        "account.analytic.plan", "search_read",
        [],
        ["id", "name", "parent_id"],
        limit=100
    )

@st.cache_data(ttl=3600)
def get_analytic_accounts(plan_id=None):
    """Haal analytische rekeningen (projecten) op, optioneel gefilterd op plan."""
    domain = []
    if plan_id:
        domain.append(["plan_id", "=", plan_id])
    return odoo_call(
        "account.analytic.account", "search_read",
        domain,
        ["id", "name", "plan_id", "code", "partner_id"],
        limit=2000,
        include_archived=True
    )

@st.cache_data(ttl=300)
def get_analytic_lines(analytic_account_id, year=None):
    """Haal analytische boekingsregels op voor een specifieke rekening.

    Retourneert een lijst met regels uit account.analytic.line.
    Positief bedrag = opbrengst, negatief bedrag = kosten.
    Zonder year-parameter worden ALLE periodes teruggegeven (projecten zijn niet jaargebonden).
    """
    domain = [["account_id", "=", analytic_account_id]]
    if year:
        domain += [
            ["date", ">=", f"{year}-01-01"],
            ["date", "<=", f"{year}-12-31"],
        ]
    return odoo_call(
        "account.analytic.line", "search_read",
        domain,
        ["id", "date", "name", "amount", "partner_id", "company_id",
         "general_account_id", "move_line_id"],
        limit=10000
    )

@st.cache_data(ttl=300)
def get_analytic_invoices(analytic_account_id, year=None):
    """Haal verkoop- én inkoopfacturen op via account.analytic.line.move_line_id.

    Retourneert een tuple: (lijst van account.move dicts, dict {move_id: proj_bedrag}).
    proj_bedrag is het bedrag dat analytisch aan dit project is toegewezen (kan kleiner
    zijn dan het factuurtotaal als de factuur meerdere projecten dekt).
    Zonder year-parameter worden ALLE periodes teruggegeven.
    """
    # Stap 1: haal analytische regels op voor dit project (incl. amount voor attributie)
    aline_domain = [["account_id", "=", analytic_account_id]]
    if year:
        aline_domain += [
            ["date", ">=", f"{year}-01-01"],
            ["date", "<=", f"{year}-12-31"],
        ]
    alines = odoo_call(
        "account.analytic.line", "search_read",
        aline_domain,
        ["move_line_id", "amount"],
        limit=10000
    )
    if not alines:
        return [], {}

    # Stap 2: bouw move_line_id → totaal analytisch bedrag mapping
    ml_to_amount = {}
    for a in alines:
        if a.get("move_line_id"):
            ml_id = a["move_line_id"][0]
            ml_to_amount[ml_id] = ml_to_amount.get(ml_id, 0) + (a.get("amount") or 0)
    if not ml_to_amount:
        return [], {}

    # Stap 3: filter op move lines die bij een factuur horen
    move_lines = odoo_call(
        "account.move.line", "search_read",
        [
            ["id", "in", list(ml_to_amount.keys())],
            ["move_id.move_type", "in", ["out_invoice", "out_refund", "in_invoice", "in_refund"]],
            ["move_id.state", "=", "posted"],
        ],
        ["id", "move_id"],
        limit=len(ml_to_amount) + 100,
        include_archived=True
    )
    if not move_lines:
        return [], {}

    # Stap 4: bereken het project-aandeel per factuur (move_id)
    move_attribution = {}  # {move_id: proj_bedrag}
    for ml in move_lines:
        if ml.get("move_id"):
            move_id = ml["move_id"][0]
            amount = ml_to_amount.get(ml["id"], 0)
            move_attribution[move_id] = move_attribution.get(move_id, 0) + amount

    # Stap 5: haal de factuurkoppen op
    move_ids = list(move_attribution.keys())
    invoices = odoo_call(
        "account.move", "search_read",
        [["id", "in", move_ids]],
        ["id", "name", "partner_id", "invoice_date", "invoice_date_due",
         "amount_untaxed", "amount_total", "amount_residual",
         "move_type", "payment_state", "ref", "company_id"],
        limit=len(move_ids) + 100,
        include_archived=True
    ) or []
    return invoices, move_attribution

@st.cache_data(ttl=300)
def get_analytic_all_invoices(analytic_account_id):
    """Haal alle facturen op (verkoop én inkoop) gekoppeld aan een analytische rekening.

    Wordt gebruikt voor de detail drill-down in het Margerisico overzicht.
    """
    # Vind factuurregels via account.analytic.line (betrouwbaar)
    alines = odoo_call(
        "account.analytic.line", "search_read",
        [["account_id", "=", analytic_account_id]],
        ["move_line_id"],
        limit=10000
    )
    ml_ids = list({a["move_line_id"][0] for a in alines
                   if a.get("move_line_id")})
    if not ml_ids:
        return []

    lines = odoo_call(
        "account.move.line", "search_read",
        [
            ["id", "in", ml_ids],
            ["move_id.move_type", "in",
             ["out_invoice", "out_refund", "in_invoice", "in_refund"]],
            ["move_id.state", "=", "posted"],
        ],
        ["move_id"],
        limit=len(ml_ids) + 100,
        include_archived=True
    )
    if not lines:
        return []

    move_ids = list({l["move_id"][0] for l in lines if l.get("move_id")})
    return odoo_call(
        "account.move", "search_read",
        [["id", "in", move_ids]],
        ["name", "partner_id", "invoice_date", "invoice_date_due",
         "amount_untaxed", "amount_total", "amount_residual",
         "move_type", "payment_state", "ref", "company_id"],
        limit=len(move_ids) + 100,
        include_archived=True
    ) or []

@st.cache_data(ttl=300)
def get_analytic_invoices_with_share(analytic_account_id):
    """Haal facturen op met het projectaandeel berekend via analytic_distribution.

    Voor facturen die over meerdere projecten verdeeld zijn, wordt per factuurregel
    het percentage uit analytic_distribution gebruikt om het projectaandeel te berekenen.
    Retourneert facturen met extra velden:
      - proj_share_untaxed  : projectaandeel excl. BTW
      - proj_share_pct      : projectpercentage (0-100)
      - proj_share_residual : projectaandeel openstaand bedrag
    """
    import json as _json

    # Stap 1a: vind factuurregels via account.analytic.line (betrouwbaar,
    #          werkt ook als ilike niet ondersteund is op jsonb-velden)
    alines = odoo_call(
        "account.analytic.line", "search_read",
        [["account_id", "=", analytic_account_id]],
        ["move_line_id"],
        limit=10000
    )
    ml_ids = list({a["move_line_id"][0] for a in alines
                   if a.get("move_line_id")})
    if not ml_ids:
        return []

    # Stap 1b: haal factuurregels op met analytic_distribution en regelbedrag
    lines = odoo_call(
        "account.move.line", "search_read",
        [
            ["id", "in", ml_ids],
            ["move_id.move_type", "in",
             ["out_invoice", "out_refund", "in_invoice", "in_refund"]],
            ["move_id.state", "=", "posted"],
        ],
        ["move_id", "price_subtotal", "analytic_distribution"],
        limit=len(ml_ids) + 100,
        include_archived=True
    )
    if not lines:
        return []

    # Stap 2: projectaandeel per factuur berekenen
    move_share = {}  # move_id -> projectaandeel excl. BTW
    for line in lines:
        if not line.get("move_id"):
            continue
        move_id = line["move_id"][0]

        analytic_dist = line.get("analytic_distribution") or {}
        if isinstance(analytic_dist, str):
            try:
                analytic_dist = _json.loads(analytic_dist)
            except Exception:
                analytic_dist = {}

        project_pct = 0.0
        for key, pct in analytic_dist.items():
            if str(key) == str(analytic_account_id):
                project_pct = float(pct) / 100.0
                break

        line_amount = abs(line.get("price_subtotal") or 0)
        move_share[move_id] = move_share.get(move_id, 0.0) + line_amount * project_pct

    if not move_share:
        return []

    # Stap 3: volledige factuurdata ophalen
    move_ids = list(move_share.keys())
    invoices = odoo_call(
        "account.move", "search_read",
        [["id", "in", move_ids]],
        ["name", "partner_id", "invoice_date", "invoice_date_due",
         "amount_untaxed", "amount_total", "amount_residual",
         "move_type", "payment_state", "ref", "company_id"],
        limit=len(move_ids) + 100,
        include_archived=True
    ) or []

    # Stap 4: projectaandeel toevoegen aan elk factuurrecord
    for inv in invoices:
        proj_share = move_share.get(inv["id"], 0.0)
        total_untaxed = abs(inv.get("amount_untaxed") or 0)
        proj_pct = (proj_share / total_untaxed) if total_untaxed else 0.0
        inv["proj_share_untaxed"] = proj_share
        inv["proj_share_pct"] = round(proj_pct * 100, 1)
        inv["proj_share_residual"] = abs(inv.get("amount_residual") or 0) * proj_pct

    return invoices

@st.cache_data(ttl=300)
def get_all_analytic_summaries(plan_id):
    """Haal financiële samenvatting op voor ALLE analytische rekeningen onder een plan.

    Gebruikt twee server-side read_groups (opbrengsten en kosten) in plaats van
    per-project queries, om het aantal API-calls minimaal te houden.
    Geen jaarfilter – toont de totale projectstand over alle periodes.
    """
    accounts = get_analytic_accounts(plan_id)
    if not accounts:
        return []

    account_ids = [a["id"] for a in accounts]

    # Server-side aggregatie: opbrengsten (amount > 0) per account
    rev_groups = odoo_read_group(
        "account.analytic.line",
        [["account_id", "in", account_ids], ["amount", ">", 0]],
        ["amount:sum"],
        ["account_id"]
    )
    # Server-side aggregatie: kosten (amount < 0) per account
    cost_groups = odoo_read_group(
        "account.analytic.line",
        [["account_id", "in", account_ids], ["amount", "<", 0]],
        ["amount:sum"],
        ["account_id"]
    )

    rev_map = {
        r["account_id"][0]: r.get("amount", 0) or 0
        for r in rev_groups if r.get("account_id")
    }
    cost_map = {
        c["account_id"][0]: abs(c.get("amount", 0) or 0)
        for c in cost_groups if c.get("account_id")
    }

    summaries = []
    for acc in accounts:
        acc_id = acc["id"]
        code = acc.get("code") or ""
        name = acc.get("name", "")
        label = f"{code} – {name}".strip("– ") if code else name
        opbrengst = rev_map.get(acc_id, 0)
        kosten = cost_map.get(acc_id, 0)
        resultaat = opbrengst - kosten
        marge_pct = resultaat / opbrengst * 100 if opbrengst else None
        summaries.append({
            "id": acc_id,
            "Project": label,
            "Opbrengst": opbrengst,
            "Kosten": kosten,
            "Resultaat": resultaat,
            "Marge %": marge_pct,
        })

    return sorted(summaries, key=lambda x: x.get("Resultaat", 0))

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

# Budget and balance mapping storage paths
BUDGET_STORAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "budget_data.json")
BALANCE_MAPPING_STORAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "balance_mapping.json")

# ---------------------------------------------------------------------------
# P&L structuur uitbreiding op geaggregeerd rapportageniveau
# ---------------------------------------------------------------------------
REPORT_CATEGORIES.update({
    "advies": {
        "name": "Advies",
        "section": "revenue",
        "order": 6,
        "sign_flip": True,
        "account_patterns": [],
        "is_subtotal": False
    },
    "sociale_lasten": {
        "name": "Sociale lasten",
        "section": "operating_expenses",
        "order": 10.5,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "pensioenlasten": {
        "name": "Pensioenlasten",
        "section": "operating_expenses",
        "order": 10.6,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "merkrechten_donaties": {
        "name": "Merkrechten & Donaties",
        "section": "operating_expenses",
        "order": 14.5,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "kasverschil": {
        "name": "Kasverschil",
        "section": "operating_expenses",
        "order": 19.5,
        "sign_flip": False,
        "account_patterns": [],
        "is_subtotal": False
    },
    "netto_omzet_resultaat": {
        "name": "Netto-omzetresultaat",
        "section": "result",
        "order": 21,
        "is_subtotal": True,
        "calculation": "bruto_omzet_resultaat - totaal_operationele_kosten"
    }
})

# Harmoniseer benamingen met gewenste rapportstructuur
REPORT_CATEGORIES["overige_personele_kosten"]["name"] = "Overige personeelskosten"
REPORT_CATEGORIES["management_fee"]["name"] = "Managementvergoeding"
REPORT_CATEGORIES["bruto_omzet_resultaat"]["name"] = "Bruto-omzetresultaat"
REPORT_CATEGORIES["totaal_operationele_kosten"]["name"] = "Totaal Kosten"

# Werk subtotalen bij met nieuwe categorieën
REPORT_CATEGORIES["bruto_omzet_resultaat"]["calculation"] = (
    "netto_omzet - kostprijs_omzet - prijsverschillen - overige_inkoopkosten - voorraadaanpassingen + advies"
)
REPORT_CATEGORIES["totaal_operationele_kosten"]["calculation"] = (
    "lonen_salarissen + sociale_lasten + pensioenlasten + overige_personele_kosten + "
    "huisvestingskosten + verkoopkosten + merkrechten_donaties + automatiseringskosten + "
    "vervoerskosten + kantoorkosten + admin_accountantskosten + algemene_kosten + "
    "management_fee + kasverschil"
)
REPORT_CATEGORIES["resultaat_voor_belasting"]["calculation"] = "netto_omzet_resultaat - totaal_overige_lasten"

# Structuur voor mapping UI op geaggregeerd niveau
PNL_MAPPING_STRUCTURE = [
    {"key": "netto_omzet", "name": "Netto-omzet", "level": 0, "expandable": True},
    {"key": "kostprijs_omzet", "name": "Kostprijs van de omzet", "level": 0, "expandable": True},
    {"key": "prijsverschillen", "name": "Prijsverschillen", "level": 0, "expandable": True},
    {"key": "overige_inkoopkosten", "name": "Overige inkoopkosten", "level": 0, "expandable": True},
    {"key": "voorraadaanpassingen", "name": "Voorraadaanpassingen", "level": 0, "expandable": True},
    {"key": "advies", "name": "Advies", "level": 0, "expandable": True},
    {"key": None, "name": "Bruto Marge %", "level": 1, "is_subtotal": True},
    {"key": None, "name": "Bruto Marge inkoop %", "level": 1, "is_subtotal": True},
    {"key": None, "name": "Totaal Bruto-omzetresultaat", "level": 0, "is_subtotal": True},
    {"key": None, "name": "Kosten", "level": 0, "is_header": True},
    {"key": "lonen_salarissen", "name": "Lonen en salarissen", "level": 1, "expandable": True},
    {"key": "sociale_lasten", "name": "Sociale lasten", "level": 1, "expandable": True},
    {"key": "pensioenlasten", "name": "Pensioenlasten", "level": 1, "expandable": True},
    {"key": "overige_personele_kosten", "name": "Overige personeelskosten", "level": 1, "expandable": True},
    {"key": "huisvestingskosten", "name": "Huisvestingskosten", "level": 1, "expandable": True},
    {"key": "verkoopkosten", "name": "Verkoopkosten", "level": 1, "expandable": True},
    {"key": "merkrechten_donaties", "name": "Merkrechten & Donaties", "level": 1, "expandable": True},
    {"key": "automatiseringskosten", "name": "Automatiseringskosten", "level": 1, "expandable": True},
    {"key": "vervoerskosten", "name": "Vervoerskosten", "level": 1, "expandable": True},
    {"key": "kantoorkosten", "name": "Kantoorkosten", "level": 1, "expandable": True},
    {"key": "admin_accountantskosten", "name": "Administratie & Accountantskosten", "level": 1, "expandable": True},
    {"key": "algemene_kosten", "name": "Algemene kosten", "level": 1, "expandable": True},
    {"key": "management_fee", "name": "Managementvergoeding", "level": 1, "expandable": True},
    {"key": "kasverschil", "name": "Kasverschil", "level": 1, "expandable": True},
    {"key": None, "name": "Totaal Kosten", "level": 0, "is_subtotal": True},
    {"key": None, "name": "Netto-omzetresultaat", "level": 0, "is_subtotal": True},
    {"key": "financieel_resultaat", "name": "Financieel resultaat", "level": 0, "expandable": True},
    {"key": "afschrijvingen", "name": "Afschrijvingen", "level": 0, "expandable": True},
    {"key": "belastingen", "name": "Belastingen", "level": 0, "expandable": True},
]

# Balance leaf categories for Activa/Passiva structuur
BALANCE_CATEGORY_DEFINITIONS = {
    # ACTIVA
    "goodwill": {"name": "Goodwill", "section": "activa", "group": "immateriele_vaste_activa", "order": 1, "sign_flip": False},
    "concessies_vergunningen_ie": {"name": "Concessies, vergunningen en intellectuele eigendommen", "section": "activa", "group": "immateriele_vaste_activa", "order": 2, "sign_flip": False},
    "kosten_van_ontwikkeling": {"name": "Kosten van ontwikkeling", "section": "activa", "group": "immateriele_vaste_activa", "order": 3, "sign_flip": False},
    "gebouwen_verbouwing": {"name": "Gebouwen & Verbouwing", "section": "activa", "group": "materiele_vaste_activa", "order": 4, "sign_flip": False},
    "machines_installaties": {"name": "Machines en Installaties", "section": "activa", "group": "materiele_vaste_activa", "order": 5, "sign_flip": False},
    "inventaris": {"name": "Inventaris", "section": "activa", "group": "materiele_vaste_activa", "order": 6, "sign_flip": False},
    "vervoermiddelen": {"name": "Vervoermiddelen", "section": "activa", "group": "materiele_vaste_activa", "order": 7, "sign_flip": False},
    "financiele_vaste_activa": {"name": "Financiële Vaste Activa", "section": "activa", "group": "vaste_activa_overig", "order": 8, "sign_flip": False},
    "gereed_product_handelsgoederen": {"name": "Gereed product en handelsgoederen", "section": "activa", "group": "voorraden", "order": 9, "sign_flip": False},
    "vooruitbetaald_voorraden": {"name": "Vooruitbetaald op voorraden", "section": "activa", "group": "voorraden", "order": 10, "sign_flip": False},
    "handelsdebiteuren": {"name": "Handelsdebiteuren", "section": "activa", "group": "vorderingen", "order": 11, "sign_flip": False},
    "vorderingen_op_groepsmaatschappijen": {"name": "Vorderingen op groepsmaatschappijen", "section": "activa", "group": "vorderingen", "order": 12, "sign_flip": False},
    "belasting_premies_sociale_zekerheid_activa": {"name": "Belasting en premies sociale zekerheid", "section": "activa", "group": "vorderingen", "order": 13, "sign_flip": False},
    "overige_vorderingen": {"name": "Overige vorderingen", "section": "activa", "group": "vorderingen", "order": 14, "sign_flip": False},
    "overlopende_activa": {"name": "Overlopende activa", "section": "activa", "group": "vorderingen", "order": 15, "sign_flip": False},
    "liquide_middelen": {"name": "Liquide Middelen", "section": "activa", "group": "liquide_middelen", "order": 16, "sign_flip": False},
    # PASSIVA
    "gestort_opgevraagd_kapitaal": {"name": "Gestort en Opgevraagd Kapitaal", "section": "passiva", "group": "eigen_vermogen", "order": 101, "sign_flip": True},
    "agio": {"name": "Agio", "section": "passiva", "group": "eigen_vermogen", "order": 102, "sign_flip": True},
    "herwaarderingsreserve": {"name": "Herwaarderingsreserve", "section": "passiva", "group": "eigen_vermogen", "order": 103, "sign_flip": True},
    "wettelijke_statutaire_reserves": {"name": "Wettelijke en statutaire reserves", "section": "passiva", "group": "eigen_vermogen", "order": 104, "sign_flip": True},
    "overige_reserves": {"name": "Overige Reserves", "section": "passiva", "group": "eigen_vermogen", "order": 105, "sign_flip": True},
    "onverdeelde_winst": {"name": "Onverdeelde Winst", "section": "passiva", "group": "eigen_vermogen", "order": 106, "sign_flip": True},
    "voorzieningen": {"name": "Voorzieningen", "section": "passiva", "group": "schulden_voorzieningen", "order": 107, "sign_flip": True},
    "schulden_aan_kredietinstellingen": {"name": "Schulden aan kredietinstellingen", "section": "passiva", "group": "langlopende_schulden", "order": 108, "sign_flip": True},
    "schulden_aan_groepsmaatschappijen": {"name": "Schulden aan groepsmaatschappijen", "section": "passiva", "group": "kortlopende_schulden", "order": 109, "sign_flip": True},
    "aflossingsverplichtingen": {"name": "Aflossingsverplichtingen", "section": "passiva", "group": "kortlopende_schulden", "order": 110, "sign_flip": True},
    "crediteuren": {"name": "Crediteuren", "section": "passiva", "group": "kortlopende_schulden", "order": 111, "sign_flip": True},
    "omzetbelasting": {"name": "Omzetbelasting", "section": "passiva", "group": "belasting_premies_passiva", "order": 112, "sign_flip": True},
    "premies_pensioen": {"name": "Premies Pensioen", "section": "passiva", "group": "belasting_premies_passiva", "order": 113, "sign_flip": True},
    "loonheffing": {"name": "Loonheffing", "section": "passiva", "group": "belasting_premies_passiva", "order": 114, "sign_flip": True},
    "vennootschapsbelasting": {"name": "Vennootschapsbelasting", "section": "passiva", "group": "belasting_premies_passiva", "order": 115, "sign_flip": True},
    "overige_schulden": {"name": "Overige schulden", "section": "passiva", "group": "kortlopende_schulden", "order": 116, "sign_flip": True},
    "overlopende_passiva": {"name": "Overlopende passiva", "section": "passiva", "group": "kortlopende_schulden", "order": 117, "sign_flip": True},
}

MONTH_LABELS_NL = {
    1: "Jan", 2: "Feb", 3: "Mrt", 4: "Apr", 5: "Mei", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Okt", 11: "Nov", 12: "Dec"
}

# Rule-based auto-mapping (prefix + optional naam-woorden)
PNL_AUTO_MAPPING_RULES = [
    {"category": "netto_omzet", "prefixes": ["80", "81", "82", "83", "84", "85"], "keywords": []},
    {"category": "kostprijs_omzet", "prefixes": ["70", "71", "72", "73", "74", "75"], "keywords": []},
    {"category": "prijsverschillen", "prefixes": [], "keywords": ["prijsverschil"]},
    {"category": "overige_inkoopkosten", "prefixes": [], "keywords": ["inkoop", "grondstof", "handelsgoederen"]},
    {"category": "voorraadaanpassingen", "prefixes": [], "keywords": ["voorraad", "voorraadaanpassing"]},
    {"category": "advies", "prefixes": [], "keywords": ["advies"]},
    {"category": "lonen_salarissen", "prefixes": ["620", "621"], "keywords": ["loon", "salaris", "brutoloon"]},
    {"category": "sociale_lasten", "prefixes": ["622"], "keywords": ["sociale lasten", "sociale zekerheid", "svw", "zvw"]},
    {"category": "pensioenlasten", "prefixes": ["623"], "keywords": ["pensioen"]},
    {"category": "overige_personele_kosten", "prefixes": ["624"], "keywords": ["personeel", "wkr", "reiskosten"]},
    {"category": "huisvestingskosten", "prefixes": ["41"], "keywords": ["huur", "huisvesting", "energie"]},
    {"category": "verkoopkosten", "prefixes": ["44"], "keywords": ["verkoop", "marketing", "reclame"]},
    {"category": "merkrechten_donaties", "prefixes": [], "keywords": ["merkrecht", "donatie"]},
    {"category": "automatiseringskosten", "prefixes": [], "keywords": ["ict", "automatisering", "software", "licentie", "it "]},
    {"category": "vervoerskosten", "prefixes": ["42"], "keywords": ["vervoer", "transport", "auto"]},
    {"category": "kantoorkosten", "prefixes": ["43"], "keywords": ["kantoor", "print", "telefoon"]},
    {"category": "admin_accountantskosten", "prefixes": [], "keywords": ["accountant", "administratie", "juridisch"]},
    {"category": "algemene_kosten", "prefixes": ["45", "46"], "keywords": ["algemene kosten", "overige bedrijfskosten"]},
    {"category": "management_fee", "prefixes": [], "keywords": ["management fee", "managementvergoeding"]},
    {"category": "kasverschil", "prefixes": [], "keywords": ["kasverschil"]},
    {"category": "financieel_resultaat", "prefixes": ["47", "65"], "keywords": ["rente", "financieel"]},
    {"category": "afschrijvingen", "prefixes": ["48", "63"], "keywords": ["afschrijving"]},
    {"category": "belastingen", "prefixes": ["49", "67"], "keywords": ["belasting", "vennootschapsbelasting"]},
]

BALANCE_AUTO_MAPPING_RULES = [
    {"category": "goodwill", "prefixes": [], "keywords": ["goodwill"]},
    {"category": "concessies_vergunningen_ie", "prefixes": [], "keywords": ["concess", "vergunning", "intellect"]},
    {"category": "kosten_van_ontwikkeling", "prefixes": [], "keywords": ["ontwikkeling"]},
    {"category": "gebouwen_verbouwing", "prefixes": [], "keywords": ["gebouw", "verbouwing"]},
    {"category": "machines_installaties", "prefixes": [], "keywords": ["machine", "installatie"]},
    {"category": "inventaris", "prefixes": [], "keywords": ["inventaris"]},
    {"category": "vervoermiddelen", "prefixes": [], "keywords": ["vervoermiddel", "auto"]},
    {"category": "financiele_vaste_activa", "prefixes": [], "keywords": ["financiele vaste activa", "deelneming"]},
    {"category": "gereed_product_handelsgoederen", "prefixes": [], "keywords": ["gereed product", "handelsgoederen", "voorraad"]},
    {"category": "vooruitbetaald_voorraden", "prefixes": [], "keywords": ["vooruitbetaald"]},
    {"category": "handelsdebiteuren", "prefixes": [], "keywords": ["debiteur"]},
    {"category": "vorderingen_op_groepsmaatschappijen", "prefixes": [], "keywords": ["vordering", "groepsmaatschappij"]},
    {"category": "belasting_premies_sociale_zekerheid_activa", "prefixes": [], "keywords": ["belasting", "premies sociale zekerheid"]},
    {"category": "overige_vorderingen", "prefixes": [], "keywords": ["overige vorderingen"]},
    {"category": "overlopende_activa", "prefixes": [], "keywords": ["overlopende activa"]},
    {"category": "liquide_middelen", "prefixes": ["10", "11"], "keywords": ["bank", "kas", "liquide"]},
    {"category": "gestort_opgevraagd_kapitaal", "prefixes": [], "keywords": ["kapitaal"]},
    {"category": "agio", "prefixes": [], "keywords": ["agio"]},
    {"category": "herwaarderingsreserve", "prefixes": [], "keywords": ["herwaarderingsreserve"]},
    {"category": "wettelijke_statutaire_reserves", "prefixes": [], "keywords": ["wettelijke", "statutaire reserves"]},
    {"category": "overige_reserves", "prefixes": [], "keywords": ["overige reserves"]},
    {"category": "onverdeelde_winst", "prefixes": [], "keywords": ["onverdeelde winst", "resultaat"]},
    {"category": "voorzieningen", "prefixes": [], "keywords": ["voorziening"]},
    {"category": "schulden_aan_kredietinstellingen", "prefixes": [], "keywords": ["kredietinstelling", "lening"]},
    {"category": "schulden_aan_groepsmaatschappijen", "prefixes": [], "keywords": ["schuld", "groepsmaatschappij", "r/c"]},
    {"category": "aflossingsverplichtingen", "prefixes": [], "keywords": ["aflossing"]},
    {"category": "crediteuren", "prefixes": [], "keywords": ["crediteur"]},
    {"category": "omzetbelasting", "prefixes": [], "keywords": ["omzetbelasting", "btw"]},
    {"category": "premies_pensioen", "prefixes": [], "keywords": ["premies pensioen"]},
    {"category": "loonheffing", "prefixes": [], "keywords": ["loonheffing"]},
    {"category": "vennootschapsbelasting", "prefixes": [], "keywords": ["vennootschapsbelasting"]},
    {"category": "overige_schulden", "prefixes": [], "keywords": ["overige schulden"]},
    {"category": "overlopende_passiva", "prefixes": [], "keywords": ["overlopende passiva"]},
]

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

    auto_col1, auto_col2 = st.columns([1.4, 2.6])
    with auto_col1:
        if st.button("⚡ Auto-map (adviesregels)", key="auto_map_pnl"):
            mapped_count = apply_auto_mapping_rules(
                mapping=mapping,
                accounts=available_accounts,
                rules=PNL_AUTO_MAPPING_RULES,
                category_keys=get_leaf_report_category_keys(),
            )
            st.session_state.draggable_mapping = mapping
            st.success(f"{mapped_count} rekening(en) automatisch toegewezen.")
            st.rerun()
    with auto_col2:
        st.caption("Gebaseerd op rekeningprefix + naamherkenning. Controleer daarna handmatig.")
    st.markdown("---")

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
        report_structure = PNL_MAPPING_STRUCTURE

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
        results[cat_key] = _evaluate_calculation(calculation, results)

    return results


def get_leaf_report_category_keys():
    """Return report categories that require direct account mapping (non-subtotals)."""
    return [k for k, v in REPORT_CATEGORIES.items() if not v.get("is_subtotal", False)]


def get_sorted_report_categories(include_subtotals=True):
    """Return ordered list of category keys based on configured order."""
    keys = []
    for key, info in sorted(REPORT_CATEGORIES.items(), key=lambda item: item[1].get("order", 999)):
        if include_subtotals or not info.get("is_subtotal", False):
            keys.append(key)
    return keys


def _evaluate_calculation(calculation, values_by_key):
    """
    Safely evaluate subtotal expressions against a dict with category values.
    """
    expr = calculation
    for key, value in values_by_key.items():
        expr = re.sub(rf"\b{re.escape(key)}\b", str(value), expr)

    allowed_chars = set("0123456789.+-*/() ")
    clean_expr = "".join(ch for ch in expr if ch in allowed_chars)
    try:
        return float(eval(clean_expr))
    except Exception:
        return 0.0


def _month_to_int(raw_month):
    """Parse month from int/string/date-like labels (supports EN/NL labels)."""
    if raw_month is None:
        return None

    if isinstance(raw_month, int):
        return raw_month if 1 <= raw_month <= 12 else None

    s = str(raw_month).strip()
    if not s:
        return None

    if s.isdigit():
        m = int(s)
        return m if 1 <= m <= 12 else None

    # ISO-like values e.g. 2026-03
    if re.match(r"^\d{4}-\d{2}", s):
        try:
            m = int(s[5:7])
            return m if 1 <= m <= 12 else None
        except Exception:
            pass

    name_map = {
        "january": 1, "januari": 1,
        "february": 2, "februari": 2,
        "march": 3, "maart": 3,
        "april": 4,
        "may": 5, "mei": 5,
        "june": 6, "juni": 6,
        "july": 7, "juli": 7,
        "august": 8, "augustus": 8,
        "september": 9,
        "october": 10, "oktober": 10,
        "november": 11,
        "december": 12,
    }

    parts = re.split(r"[\s\-/_,]+", s.lower())
    for part in parts:
        if part in name_map:
            return name_map[part]

    return None


def _parse_amount(raw_value):
    """Parse numeric amounts from NL/EN formatted strings."""
    if raw_value is None or (isinstance(raw_value, float) and pd.isna(raw_value)):
        return None
    if isinstance(raw_value, (int, float)):
        return float(raw_value)

    s = str(raw_value).strip().replace("€", "").replace(" ", "")
    if not s:
        return None

    if "," in s and "." in s:
        # decide decimal separator by last occurrence
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        return float(s)
    except Exception:
        return None


def _ensure_mapping_shape(mapping):
    """Ensure loaded mapping contains all expected report category containers."""
    if "categories" not in mapping or not isinstance(mapping["categories"], dict):
        mapping["categories"] = {}
    for cat_key in get_leaf_report_category_keys():
        mapping["categories"].setdefault(cat_key, [])
    return mapping


def _account_matches_rule(account_code, account_name, rule):
    """Check if account matches rule by prefix and/or keyword."""
    code = str(account_code or "").strip()
    name = str(account_name or "").lower()
    prefixes = rule.get("prefixes", [])
    keywords = [k.lower() for k in rule.get("keywords", [])]

    prefix_hit = any(code.startswith(prefix) for prefix in prefixes) if prefixes else False
    keyword_hit = any(keyword in name for keyword in keywords) if keywords else False

    if prefixes and keywords:
        return prefix_hit or keyword_hit
    if prefixes:
        return prefix_hit
    if keywords:
        return keyword_hit
    return False


def apply_auto_mapping_rules(mapping, accounts, rules, category_keys):
    """
    Apply auto-mapping rules.
    - keeps 1-op-1 mapping
    - only assigns currently unassigned accounts
    Returns number of assigned accounts.
    """
    mapping.setdefault("categories", {})
    for key in category_keys:
        mapping["categories"].setdefault(key, [])

    assigned_codes = set()
    for key in category_keys:
        for code in mapping["categories"].get(key, []):
            assigned_codes.add(code)

    auto_assigned = 0
    for acc in sorted(accounts, key=lambda a: a.get("code", "")):
        code = acc.get("code", "")
        name = acc.get("name", "")
        if code in assigned_codes:
            continue

        for rule in rules:
            target = rule.get("category")
            if target not in category_keys:
                continue
            if _account_matches_rule(code, name, rule):
                mapping["categories"][target].append(code)
                assigned_codes.add(code)
                auto_assigned += 1
                break

    return auto_assigned


def load_budget_entries():
    """Load persisted budget entries."""
    try:
        if os.path.exists(BUDGET_STORAGE_FILE):
            with open(BUDGET_STORAGE_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                return payload.get("entries", [])
            if isinstance(payload, list):
                return payload
    except Exception as e:
        print(f"Error loading budget entries: {e}")
    return []


def save_budget_entries(entries):
    """Persist budget entries to disk."""
    try:
        payload = {
            "last_modified": datetime.now().isoformat(),
            "entries": entries,
        }
        with open(BUDGET_STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True, "Budget opgeslagen"
    except Exception as e:
        return False, f"Opslaan budget mislukt: {e}"


def build_budget_template_dataframe(year, company_ids=None):
    """Create a budget template at report-line level per company/month."""
    rows = []
    if company_ids is None:
        company_ids = list(COMPANIES.keys())

    leaf_keys = get_leaf_report_category_keys()
    for comp_id in company_ids:
        comp_name = COMPANIES.get(comp_id, f"Company {comp_id}")
        for month in range(1, 13):
            for cat_key in leaf_keys:
                rows.append({
                    "year": year,
                    "company_id": comp_id,
                    "company_name": comp_name,
                    "month": month,
                    "month_label": MONTH_LABELS_NL[month],
                    "category_key": cat_key,
                    "category_name": REPORT_CATEGORIES[cat_key]["name"],
                    "amount": 0.0,
                })
    return pd.DataFrame(rows)


def build_budget_template_excel(year, company_ids=None):
    """Create Excel template with instructions + masterdata + budget input."""
    template_df = build_budget_template_dataframe(year, company_ids=company_ids)

    instructions_df = pd.DataFrame([
        {"kolom": "year", "verplicht": "ja", "omschrijving": "Kalenderjaar (bijv. 2026)", "voorbeeld": year},
        {"kolom": "company_id", "verplicht": "ja (of company_name)", "omschrijving": "Bedrijfs-ID", "voorbeeld": 1},
        {"kolom": "company_name", "verplicht": "ja (of company_id)", "omschrijving": "Bedrijfsnaam", "voorbeeld": "LAB Conceptstore"},
        {"kolom": "month", "verplicht": "ja", "omschrijving": "Maandnummer 1-12", "voorbeeld": 1},
        {"kolom": "category_key", "verplicht": "ja (of category_name)", "omschrijving": "Interne rapportregelcode", "voorbeeld": "netto_omzet"},
        {"kolom": "category_name", "verplicht": "ja (of category_key)", "omschrijving": "Rapportregelnaam", "voorbeeld": "Netto Omzet"},
        {"kolom": "amount", "verplicht": "ja", "omschrijving": "Budgetbedrag (positief tonen in rapport)", "voorbeeld": 125000},
    ])

    companies_df = pd.DataFrame([
        {"company_id": cid, "company_name": cname}
        for cid, cname in COMPANIES.items()
        if company_ids is None or cid in company_ids
    ])
    categories_df = pd.DataFrame([
        {"category_key": key, "category_name": REPORT_CATEGORIES[key]["name"]}
        for key in get_leaf_report_category_keys()
    ])

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        instructions_df.to_excel(writer, sheet_name="Instructions", index=False)
        companies_df.to_excel(writer, sheet_name="Companies", index=False)
        categories_df.to_excel(writer, sheet_name="Categories", index=False)
        template_df.to_excel(writer, sheet_name="BudgetInput", index=False)
    output.seek(0)
    return output.getvalue()


def _normalize_company_id(raw_company):
    """Translate uploaded company field (id/name) to company_id."""
    if raw_company is None or (isinstance(raw_company, float) and pd.isna(raw_company)):
        return None

    if isinstance(raw_company, (int, float)):
        cid = int(raw_company)
        return cid if cid in COMPANIES else None

    company_str = str(raw_company).strip()
    if not company_str:
        return None
    if company_str.isdigit():
        cid = int(company_str)
        return cid if cid in COMPANIES else None

    company_str_lower = company_str.lower()
    for cid, cname in COMPANIES.items():
        if cname.lower() == company_str_lower:
            return cid
    return None


def _normalize_category_key(raw_category):
    """Translate uploaded category key/name to internal category key."""
    if raw_category is None or (isinstance(raw_category, float) and pd.isna(raw_category)):
        return None
    value = str(raw_category).strip()
    if not value:
        return None

    # Direct key match
    if value in REPORT_CATEGORIES and not REPORT_CATEGORIES[value].get("is_subtotal", False):
        return value

    # Case-insensitive key match
    for key in get_leaf_report_category_keys():
        if key.lower() == value.lower():
            return key

    # Name match
    value_lower = value.lower()
    for key, info in REPORT_CATEGORIES.items():
        if info.get("is_subtotal", False):
            continue
        if info.get("name", "").lower() == value_lower:
            return key

    return None


def parse_budget_upload_dataframe(df, default_company_id=None):
    """
    Validate and normalize uploaded budget data.
    Expected columns:
    - year
    - company_id/company/company_name/entiteit
    - month
    - category_key/category_name/regel/regelcode
    - amount/bedrag
    """
    normalized_cols = {str(c).strip().lower(): c for c in df.columns}

    def pick_column(candidates):
        for c in candidates:
            if c in normalized_cols:
                return normalized_cols[c]
        return None

    col_year = pick_column(["year", "jaar"])
    col_company = pick_column(["company_id", "company", "company_name", "entiteit", "bedrijf"])
    col_month = pick_column(["month", "maand"])
    col_category = pick_column(["category_key", "category_name", "regelcode", "regel", "categorie"])
    col_amount = pick_column(["amount", "bedrag", "waarde", "value"])

    missing = []
    if col_year is None:
        missing.append("year")
    if col_company is None and default_company_id is None:
        missing.append("company")
    if col_month is None:
        missing.append("month")
    if col_category is None:
        missing.append("category")
    if col_amount is None:
        missing.append("amount")

    if missing:
        return [], [f"Ontbrekende kolommen: {', '.join(missing)}"]

    parsed_entries = []
    errors = []
    for idx, row in df.iterrows():
        line_nr = idx + 2

        try:
            year = int(row[col_year])
        except Exception:
            errors.append(f"Rij {line_nr}: ongeldig jaar '{row[col_year]}'")
            continue

        if col_company is None and default_company_id is not None:
            company_id = int(default_company_id)
        else:
            company_id = _normalize_company_id(row[col_company])
            if company_id is None:
                errors.append(f"Rij {line_nr}: onbekend bedrijf '{row[col_company]}'")
                continue

        month = _month_to_int(row[col_month])
        if month is None:
            errors.append(f"Rij {line_nr}: ongeldige maand '{row[col_month]}'")
            continue

        category_key = _normalize_category_key(row[col_category])
        if category_key is None:
            errors.append(f"Rij {line_nr}: onbekende rapportregel '{row[col_category]}'")
            continue

        amount = _parse_amount(row[col_amount])
        if amount is None:
            errors.append(f"Rij {line_nr}: ongeldig bedrag '{row[col_amount]}'")
            continue

        parsed_entries.append({
            "year": year,
            "company_id": company_id,
            "month": month,
            "category_key": category_key,
            "amount": float(amount),
        })

    return parsed_entries, errors


def merge_budget_entries(existing_entries, new_entries, replace_scope="none"):
    """
    Merge uploaded entries into existing budget store.
    replace_scope:
    - none: upsert only on exact key
    - year_company: replace existing for uploaded (year, company_id) buckets first
    """
    merged = [dict(e) for e in existing_entries]
    if replace_scope == "year_company":
        scopes = {(e["year"], e["company_id"]) for e in new_entries}
        merged = [e for e in merged if (e.get("year"), e.get("company_id")) not in scopes]

    index_map = {
        (e.get("year"), e.get("company_id"), e.get("month"), e.get("category_key")): i
        for i, e in enumerate(merged)
    }

    for entry in new_entries:
        key = (entry["year"], entry["company_id"], entry["month"], entry["category_key"])
        if key in index_map:
            merged[index_map[key]]["amount"] = float(entry["amount"])
        else:
            merged.append(entry)
            index_map[key] = len(merged) - 1

    return merged


def _add_report_subtotals_monthly(base_monthly):
    """Calculate subtotal categories for monthly arrays."""
    results = {k: v[:] for k, v in base_monthly.items()}

    subtotal_keys = [
        key for key in get_sorted_report_categories(include_subtotals=True)
        if REPORT_CATEGORIES[key].get("is_subtotal", False)
    ]
    for subtotal_key in subtotal_keys:
        calc = REPORT_CATEGORIES[subtotal_key].get("calculation", "")
        series = []
        for month_idx in range(12):
            month_values = {
                k: (results.get(k, [0.0] * 12)[month_idx] if isinstance(results.get(k), list) else 0.0)
                for k in REPORT_CATEGORIES.keys()
            }
            series.append(_evaluate_calculation(calc, month_values))
        results[subtotal_key] = series
    return results


def get_budget_monthly_values(year, company_id=None):
    """Return monthly budget values by report category for a year/company scope."""
    entries = load_budget_entries()
    base_monthly = {k: [0.0] * 12 for k in get_leaf_report_category_keys()}

    for e in entries:
        if int(e.get("year", 0)) != int(year):
            continue
        if company_id and int(e.get("company_id", 0)) != int(company_id):
            continue

        cat = e.get("category_key")
        month = int(e.get("month", 0))
        amount = float(e.get("amount", 0.0))
        if cat in base_monthly and 1 <= month <= 12:
            base_monthly[cat][month - 1] += amount

    return _add_report_subtotals_monthly(base_monthly)


def calculate_monthly_report_with_mapping(company_id, year, mapping=None, exclude_intercompany=False):
    """
    Calculate monthly actuals per mapped report category.
    Supports company scope and consolidated scope (company_id=None).
    """
    if mapping is None:
        mapping = get_draggable_mapping()
    mapping = _ensure_mapping_shape(mapping)
    categories = mapping.get("categories", {})

    base_monthly = {k: [0.0] * 12 for k in get_leaf_report_category_keys()}
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"

    for cat_key in get_leaf_report_category_keys():
        cat_info = REPORT_CATEGORIES.get(cat_key, {})
        account_codes = categories.get(cat_key, [])
        if not account_codes:
            continue

        for code in account_codes:
            domain = [
                ["date", ">=", start_date],
                ["date", "<=", end_date],
                ["parent_state", "=", "posted"],
                ["account_id.code", "=like", f"{code}%"]
            ]
            if company_id:
                domain.append(["company_id", "=", company_id])
            if exclude_intercompany and INTERCOMPANY_PARTNERS:
                domain.append(["partner_id", "not in", INTERCOMPANY_PARTNERS])

            monthly_rows = odoo_read_group(
                "account.move.line",
                domain,
                ["balance:sum"],
                ["date:month"]
            )
            for item in monthly_rows:
                month = _month_to_int(item.get("date:month"))
                if not month:
                    continue
                balance = item.get("balance:sum", item.get("balance", 0)) or 0
                if cat_info.get("sign_flip", False):
                    balance = -balance
                base_monthly[cat_key][month - 1] += balance

    return _add_report_subtotals_monthly(base_monthly)


def load_balance_mapping():
    """Load persisted balance mapping."""
    try:
        if os.path.exists(BALANCE_MAPPING_STORAGE_FILE):
            with open(BALANCE_MAPPING_STORAGE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading balance mapping: {e}")
    return {}


def save_balance_mapping(mapping_data):
    """Save balance mapping to disk."""
    try:
        payload = {
            "last_modified": datetime.now().isoformat(),
            "categories": mapping_data.get("categories", {}),
        }
        with open(BALANCE_MAPPING_STORAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True, "Balans-mapping opgeslagen"
    except Exception as e:
        return False, f"Opslaan balans-mapping mislukt: {e}"


def get_balance_mapping():
    """Get balance mapping from session_state or storage."""
    if "balance_mapping" not in st.session_state:
        loaded = load_balance_mapping()
        categories = loaded.get("categories", {}) if isinstance(loaded, dict) else {}
        for key in BALANCE_CATEGORY_DEFINITIONS.keys():
            categories.setdefault(key, [])
        st.session_state.balance_mapping = {"categories": categories}
    else:
        for key in BALANCE_CATEGORY_DEFINITIONS.keys():
            st.session_state.balance_mapping["categories"].setdefault(key, [])
    return st.session_state.balance_mapping


def _move_account_to_balance_category(mapping, account_code, target_category):
    """Ensure 1-op-1 mapping by moving account to target category."""
    for cat_key, codes in mapping["categories"].items():
        if account_code in codes:
            mapping["categories"][cat_key] = [c for c in codes if c != account_code]
    if account_code not in mapping["categories"][target_category]:
        mapping["categories"][target_category].append(account_code)


def calculate_balance_snapshot_with_mapping(as_of_date, company_id=None, mapping=None, exclude_intercompany=False):
    """Calculate balance values per mapped balance leaf category."""
    if mapping is None:
        mapping = get_balance_mapping()
    categories = mapping.get("categories", {})

    if hasattr(as_of_date, "strftime"):
        date_str = as_of_date.strftime("%Y-%m-%d")
    else:
        date_str = str(as_of_date)

    results = {k: 0.0 for k in BALANCE_CATEGORY_DEFINITIONS.keys()}
    for cat_key, info in BALANCE_CATEGORY_DEFINITIONS.items():
        account_codes = categories.get(cat_key, [])
        if not account_codes:
            continue

        total = 0.0
        for code in account_codes:
            domain = [
                ["date", "<=", date_str],
                ["parent_state", "=", "posted"],
                ["account_id.code", "=like", f"{code}%"]
            ]
            if company_id:
                domain.append(["company_id", "=", company_id])
            if exclude_intercompany and INTERCOMPANY_PARTNERS:
                domain.append(["partner_id", "not in", INTERCOMPANY_PARTNERS])

            data = odoo_read_group(
                "account.move.line",
                domain,
                ["balance:sum"],
                []
            )
            if data:
                balance = data[0].get("balance:sum", data[0].get("balance", 0)) or 0
                if info.get("sign_flip", False):
                    balance = -balance
                total += balance
        results[cat_key] = total
    return results


def render_balance_mapping_tool(company_id, year):
    """Simple bulk mapping UI for balance Activa/Passiva categories."""
    mapping = get_balance_mapping()
    categories = mapping["categories"]

    with st.spinner("Balansrekeningen ophalen..."):
        available_accounts = get_all_accounts_with_details(company_id, year)
    if not available_accounts:
        st.warning("Geen rekeningen gevonden voor balans-mapping.")
        return

    assigned_codes = set()
    for codes in categories.values():
        assigned_codes.update(codes)
    unassigned_accounts = [acc for acc in available_accounts if acc["code"] not in assigned_codes]
    account_lookup = {acc["code"]: acc for acc in available_accounts}

    st.markdown("### 🏛️ Balans Mapping (Activa/Passiva)")
    st.caption("1-op-1 mapping: een rekening kan maar in één balansregel staan.")

    auto_b_col1, auto_b_col2 = st.columns([1.4, 2.6])
    with auto_b_col1:
        if st.button("⚡ Auto-map balans (adviesregels)", key="auto_map_balance"):
            mapped_count = apply_auto_mapping_rules(
                mapping=mapping,
                accounts=available_accounts,
                rules=BALANCE_AUTO_MAPPING_RULES,
                category_keys=list(BALANCE_CATEGORY_DEFINITIONS.keys()),
            )
            st.session_state.balance_mapping = mapping
            st.success(f"{mapped_count} rekening(en) automatisch toegewezen.")
            st.rerun()
    with auto_b_col2:
        st.caption("Gebaseerd op rekeningprefix + naam. Gebruik dit als startpunt en controleer per regel.")
    st.markdown("---")

    col_add, col_prefix = st.columns(2)
    with col_add:
        category_options = sorted(
            BALANCE_CATEGORY_DEFINITIONS.keys(),
            key=lambda k: BALANCE_CATEGORY_DEFINITIONS[k]["order"]
        )
        target_category = st.selectbox(
            "Doel balansregel",
            category_options,
            format_func=lambda k: BALANCE_CATEGORY_DEFINITIONS[k]["name"],
            key="bal_target_category",
        )
        selected_unassigned = st.multiselect(
            "Selecteer niet-gemapte rekeningen",
            options=[a["display"] for a in unassigned_accounts],
            key="bal_select_unassigned",
        )
        if st.button("➕ Voeg selectie toe", key="bal_add_selected", type="primary") and selected_unassigned:
            for item in selected_unassigned:
                code = item.split(" - ")[0]
                _move_account_to_balance_category(mapping, code, target_category)
            st.session_state.balance_mapping = mapping
            st.success(f"{len(selected_unassigned)} rekening(en) toegewezen.")
            st.rerun()

    with col_prefix:
        prefix_input = st.text_input(
            "Bulk op prefix (komma-gescheiden)",
            key="bal_prefix_input",
            placeholder="Bijv. 100,101,102"
        )
        if st.button("⚡ Wijs prefixen toe", key="bal_assign_prefix"):
            prefixes = [p.strip() for p in prefix_input.split(",") if p.strip()]
            matched_codes = [a["code"] for a in unassigned_accounts if any(a["code"].startswith(p) for p in prefixes)]
            if not matched_codes:
                st.info("Geen niet-gemapte rekeningen gevonden voor deze prefixen.")
            else:
                for code in matched_codes:
                    _move_account_to_balance_category(mapping, code, target_category)
                st.session_state.balance_mapping = mapping
                st.success(f"{len(matched_codes)} rekening(en) via prefix toegewezen.")
                st.rerun()

    st.markdown("---")
    left_col, right_col = st.columns([2, 1])
    with left_col:
        for cat_key in sorted(BALANCE_CATEGORY_DEFINITIONS.keys(), key=lambda k: BALANCE_CATEGORY_DEFINITIONS[k]["order"]):
            cat_name = BALANCE_CATEGORY_DEFINITIONS[cat_key]["name"]
            section = BALANCE_CATEGORY_DEFINITIONS[cat_key]["section"].upper()
            codes = categories.get(cat_key, [])
            with st.expander(f"[{section}] {cat_name} ({len(codes)})", expanded=False):
                if not codes:
                    st.caption("Geen rekeningen gekoppeld.")
                for idx, code in enumerate(codes):
                    acc_name = account_lookup.get(code, {}).get("name", "Onbekend")
                    c1, c2 = st.columns([6, 1])
                    with c1:
                        st.caption(f"`{code}` - {acc_name}")
                    with c2:
                        if st.button("✕", key=f"bal_rm_{cat_key}_{idx}"):
                            categories[cat_key] = [c for c in categories[cat_key] if c != code]
                            st.session_state.balance_mapping = mapping
                            st.rerun()

    with right_col:
        st.markdown("**Niet-gemapt (preview)**")
        st.caption(f"{len(unassigned_accounts)} rekeningen")
        for acc in unassigned_accounts[:30]:
            st.caption(f"`{acc['code']}` {acc['name'][:28]}")
        if len(unassigned_accounts) > 30:
            st.caption(f"... en {len(unassigned_accounts) - 30} meer")

    st.markdown("---")
    b1, b2 = st.columns(2)
    with b1:
        if st.button("💾 Opslaan balans-mapping", key="bal_save_mapping", type="primary"):
            ok, msg = save_balance_mapping(st.session_state.balance_mapping)
            if ok:
                st.success(msg)
            else:
                st.error(msg)
    with b2:
        if st.button("🔄 Reset balans-mapping", key="bal_reset_mapping"):
            st.session_state.balance_mapping = {
                "categories": {k: [] for k in BALANCE_CATEGORY_DEFINITIONS.keys()}
            }
            if os.path.exists(BALANCE_MAPPING_STORAGE_FILE):
                os.remove(BALANCE_MAPPING_STORAGE_FILE)
            st.success("Balans-mapping gereset.")
            st.rerun()


def render_structured_balance_report(as_of_date, company_id=None, exclude_intercompany=False):
    """Render mapped balance in Activa/Passiva format."""
    values = calculate_balance_snapshot_with_mapping(
        as_of_date=as_of_date,
        company_id=company_id,
        exclude_intercompany=exclude_intercompany
    )

    def sum_keys(keys):
        return sum(values.get(k, 0.0) for k in keys)

    # ACTIVA groups
    immaterieel = ["goodwill", "concessies_vergunningen_ie", "kosten_van_ontwikkeling"]
    materieel = ["gebouwen_verbouwing", "machines_installaties", "inventaris", "vervoermiddelen"]
    financieel_vast = ["financiele_vaste_activa"]
    voorraden = ["gereed_product_handelsgoederen", "vooruitbetaald_voorraden"]
    vorderingen = [
        "handelsdebiteuren", "vorderingen_op_groepsmaatschappijen",
        "belasting_premies_sociale_zekerheid_activa", "overige_vorderingen", "overlopende_activa"
    ]
    liquide = ["liquide_middelen"]

    # PASSIVA groups
    eigen_vermogen = [
        "gestort_opgevraagd_kapitaal", "agio", "herwaarderingsreserve",
        "wettelijke_statutaire_reserves", "overige_reserves", "onverdeelde_winst"
    ]
    voorzieningen = ["voorzieningen"]
    langlopende = ["schulden_aan_kredietinstellingen"]
    belasting_premies = ["omzetbelasting", "premies_pensioen", "loonheffing", "vennootschapsbelasting"]
    kortlopende = [
        "schulden_aan_groepsmaatschappijen", "aflossingsverplichtingen", "crediteuren",
        "overige_schulden", "overlopende_passiva"
    ]

    col_a, col_p = st.columns(2)
    with col_a:
        st.subheader("ACTIVA")
        st.markdown("**Immateriële vaste activa**")
        for key in immaterieel:
            st.caption(f"{BALANCE_CATEGORY_DEFINITIONS[key]['name']}: €{values.get(key, 0):,.2f}")
        st.markdown(f"**Totaal Immateriële vaste activa: €{sum_keys(immaterieel):,.2f}**")

        st.markdown("**Materiële vaste activa**")
        for key in materieel:
            st.caption(f"{BALANCE_CATEGORY_DEFINITIONS[key]['name']}: €{values.get(key, 0):,.2f}")
        st.markdown(f"**Totaal Materiële vaste activa: €{sum_keys(materieel):,.2f}**")

        st.caption(f"Financiële Vaste Activa: €{sum_keys(financieel_vast):,.2f}")
        totaal_vaste_activa = sum_keys(immaterieel + materieel + financieel_vast)
        st.markdown(f"**Totaal VASTE ACTIVA: €{totaal_vaste_activa:,.2f}**")

        st.markdown("**VLOTTENDE ACTIVA**")
        st.markdown("**Voorraden**")
        for key in voorraden:
            st.caption(f"{BALANCE_CATEGORY_DEFINITIONS[key]['name']}: €{values.get(key, 0):,.2f}")
        st.markdown(f"**Totaal Voorraden: €{sum_keys(voorraden):,.2f}**")

        st.markdown("**Vorderingen**")
        for key in vorderingen:
            st.caption(f"{BALANCE_CATEGORY_DEFINITIONS[key]['name']}: €{values.get(key, 0):,.2f}")
        st.markdown(f"**Totaal Vorderingen: €{sum_keys(vorderingen):,.2f}**")

        for key in liquide:
            st.caption(f"{BALANCE_CATEGORY_DEFINITIONS[key]['name']}: €{values.get(key, 0):,.2f}")
        totaal_vlottende_activa = sum_keys(voorraden + vorderingen + liquide)
        st.markdown(f"**Totaal VLOTTENDE ACTIVA: €{totaal_vlottende_activa:,.2f}**")
        totaal_activa = totaal_vaste_activa + totaal_vlottende_activa
        st.markdown(f"### Totaal ACTIVA: €{totaal_activa:,.2f}")

    with col_p:
        st.subheader("PASSIVA")
        st.markdown("**EIGEN VERMOGEN**")
        for key in eigen_vermogen:
            st.caption(f"{BALANCE_CATEGORY_DEFINITIONS[key]['name']}: €{values.get(key, 0):,.2f}")
        st.markdown(f"**Totaal EIGEN VERMOGEN: €{sum_keys(eigen_vermogen):,.2f}**")

        st.markdown("**SCHULDEN**")
        for key in voorzieningen:
            st.caption(f"{BALANCE_CATEGORY_DEFINITIONS[key]['name']}: €{values.get(key, 0):,.2f}")
        st.markdown("**Langlopende schulden**")
        for key in langlopende:
            st.caption(f"{BALANCE_CATEGORY_DEFINITIONS[key]['name']}: €{values.get(key, 0):,.2f}")
        st.markdown(f"**Totaal Langlopende schulden: €{sum_keys(langlopende):,.2f}**")

        st.markdown("**Kortlopende Schulden**")
        for key in ["schulden_aan_groepsmaatschappijen", "aflossingsverplichtingen", "crediteuren"]:
            st.caption(f"{BALANCE_CATEGORY_DEFINITIONS[key]['name']}: €{values.get(key, 0):,.2f}")

        st.markdown("**Belasting en Premies sociale zekerheid**")
        for key in belasting_premies:
            st.caption(f"{BALANCE_CATEGORY_DEFINITIONS[key]['name']}: €{values.get(key, 0):,.2f}")
        st.markdown(f"**Totaal Belasting en Premies sociale zekerheid: €{sum_keys(belasting_premies):,.2f}**")

        for key in ["overige_schulden", "overlopende_passiva"]:
            st.caption(f"{BALANCE_CATEGORY_DEFINITIONS[key]['name']}: €{values.get(key, 0):,.2f}")

        totaal_kortlopend = sum_keys(kortlopende + belasting_premies)
        st.markdown(f"**Totaal Kortlopende Schulden: €{totaal_kortlopend:,.2f}**")
        totaal_schulden = sum_keys(voorzieningen + langlopende) + totaal_kortlopend
        st.markdown(f"**Totaal SCHULDEN: €{totaal_schulden:,.2f}**")
        totaal_passiva = sum_keys(eigen_vermogen) + totaal_schulden
        st.markdown(f"### Totaal PASSIVA: €{totaal_passiva:,.2f}")

    st.markdown("---")
    verschil = (sum_keys(immaterieel + materieel + financieel_vast + voorraden + vorderingen + liquide)
                - (sum_keys(eigen_vermogen) + sum_keys(voorzieningen + langlopende + kortlopende + belasting_premies)))
    if abs(verschil) < 1:
        st.success(f"✅ Balans in evenwicht (verschil: €{verschil:,.2f})")
    else:
        st.warning(f"⚠️ Balansverschil: €{verschil:,.2f}")


def render_budget_import_tab(selected_year):
    """UI for downloading budget template and importing budget lines."""
    st.markdown("### 📥 Budget inlezen op rapportregelniveau")
    st.caption("Verplicht: year, month, category (key/naam), amount. Bedrijf kan in bestand of via import-scope.")

    tpl_col1, tpl_col2 = st.columns([1.2, 2.8])
    with tpl_col1:
        template_scope = st.radio(
            "Template scope",
            ["Alle bedrijven", "Eén bedrijf"],
            key="budget_template_scope"
        )
    with tpl_col2:
        template_company_id = None
        if template_scope == "Eén bedrijf":
            template_company_name = st.selectbox(
                "Template bedrijf",
                options=list(COMPANIES.values()),
                key="budget_template_company"
            )
            template_company_id = [cid for cid, cname in COMPANIES.items() if cname == template_company_name][0]

    template_company_ids = [template_company_id] if template_company_id else None
    template_df = build_budget_template_dataframe(selected_year, company_ids=template_company_ids)
    template_csv = template_df.to_csv(index=False, sep=";").encode("utf-8")
    template_xlsx = build_budget_template_excel(selected_year, company_ids=template_company_ids)

    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "📄 Download template (CSV)",
            data=template_csv,
            file_name=f"budget_template_{selected_year}.csv",
            mime="text/csv",
            key="budget_template_download_csv",
        )
    with dl2:
        st.download_button(
            "📘 Download template (Excel met tabs)",
            data=template_xlsx,
            file_name=f"budget_template_{selected_year}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="budget_template_download_xlsx",
        )

    uploaded = st.file_uploader(
        "Upload budgetbestand (CSV of Excel)",
        type=["csv", "xlsx", "xls"],
        key="budget_upload_file"
    )

    import_scope_col1, import_scope_col2 = st.columns([1.2, 2.8])
    with import_scope_col1:
        import_scope = st.radio(
            "Importscope",
            ["Bedrijf in bestand", "Geforceerd één bedrijf"],
            key="budget_import_scope"
        )
    with import_scope_col2:
        forced_company_id = None
        if import_scope == "Geforceerd één bedrijf":
            forced_company_name = st.selectbox(
                "Doelbedrijf voor alle regels in upload",
                options=list(COMPANIES.values()),
                key="budget_forced_company"
            )
            forced_company_id = [cid for cid, cname in COMPANIES.items() if cname == forced_company_name][0]

    replace_scope = st.selectbox(
        "Importmodus",
        options=["Upsert (bestaande regels overschrijven op sleutel)", "Vervang per jaar+bedrijf in upload"],
        key="budget_import_mode",
    )

    if uploaded is not None:
        try:
            if uploaded.name.lower().endswith(".csv"):
                import_df = pd.read_csv(uploaded, sep=None, engine="python")
            else:
                import_df = pd.read_excel(uploaded)
            st.write(f"Voorbeeld ({min(len(import_df), 20)} rijen):")
            st.dataframe(import_df.head(20), use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Bestand kon niet worden gelezen: {e}")
            return

        if st.button("⬆️ Verwerk budgetimport", key="budget_import_btn", type="primary"):
            parsed_entries, errors = parse_budget_upload_dataframe(
                import_df,
                default_company_id=forced_company_id
            )
            if errors:
                st.error("Import validatie-fouten gevonden:")
                for err in errors[:40]:
                    st.caption(f"- {err}")
                if len(errors) > 40:
                    st.caption(f"... en {len(errors) - 40} extra fouten")
                return

            existing_entries = load_budget_entries()
            merged_entries = merge_budget_entries(
                existing_entries,
                parsed_entries,
                replace_scope="year_company" if replace_scope.startswith("Vervang") else "none"
            )
            ok, msg = save_budget_entries(merged_entries)
            if ok:
                st.success(f"{msg} ({len(parsed_entries)} regels verwerkt)")
            else:
                st.error(msg)

    # Current year summary
    entries = [e for e in load_budget_entries() if int(e.get("year", 0)) == int(selected_year)]
    if entries:
        st.markdown("---")
        st.markdown("### 📊 Ingelezen budgetsamenvatting")
        summary_rows = []
        for comp_id, comp_name in COMPANIES.items():
            total = sum(float(e.get("amount", 0)) for e in entries if int(e.get("company_id", 0)) == comp_id)
            count = sum(1 for e in entries if int(e.get("company_id", 0)) == comp_id)
            summary_rows.append({"Bedrijf": comp_name, "Regels": count, "Budget Totaal": total})
        df_summary = pd.DataFrame(summary_rows)
        st.dataframe(
            df_summary.style.format({"Budget Totaal": "€{:,.0f}"}),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info(f"Nog geen budgetregels gevonden voor {selected_year}.")


def render_variance_analysis_tab(selected_year, report_company_id=None, exclude_intercompany=True):
    """UI for monthly variance analysis (Actual vs Budget) on mapped level."""
    st.markdown("### 📊 Variantieanalyse per maand (zelfde aggregatieniveau)")

    if report_company_id is None and exclude_intercompany:
        st.info("Intercompany-eliminatie is toegepast op actuals. Budgetregels blijven zoals ingelezen.")

    with st.spinner("Actuals en budget laden..."):
        actual = calculate_monthly_report_with_mapping(
            company_id=report_company_id,
            year=selected_year,
            exclude_intercompany=exclude_intercompany,
        )
        budget = get_budget_monthly_values(
            year=selected_year,
            company_id=report_company_id,
        )

    month_options = [f"{MONTH_LABELS_NL[m]} ({m})" for m in range(1, 13)]
    selected_month_label = st.selectbox("Maand", month_options, index=datetime.now().month - 1, key="var_month_select")
    selected_month = int(selected_month_label.split("(")[1].replace(")", ""))
    month_idx = selected_month - 1

    rows = []
    for cat_key in get_sorted_report_categories(include_subtotals=True):
        name = REPORT_CATEGORIES[cat_key]["name"]
        act_series = actual.get(cat_key, [0.0] * 12)
        bud_series = budget.get(cat_key, [0.0] * 12)
        act_val = act_series[month_idx]
        bud_val = bud_series[month_idx]
        var_val = act_val - bud_val
        var_pct = (var_val / bud_val * 100) if bud_val else 0.0
        act_ytd = sum(act_series[:month_idx + 1])
        bud_ytd = sum(bud_series[:month_idx + 1])
        var_ytd = act_ytd - bud_ytd
        var_ytd_pct = (var_ytd / bud_ytd * 100) if bud_ytd else 0.0
        rows.append({
            "Regel": name,
            "Actual maand": act_val,
            "Budget maand": bud_val,
            "Variantie maand": var_val,
            "Variantie maand %": var_pct,
            "Actual YTD": act_ytd,
            "Budget YTD": bud_ytd,
            "Variantie YTD": var_ytd,
            "Variantie YTD %": var_ytd_pct,
            "_subtotal": REPORT_CATEGORIES[cat_key].get("is_subtotal", False)
        })

    df_month = pd.DataFrame(rows)
    netto_key = "Netto-omzetresultaat"
    if netto_key in df_month["Regel"].values:
        net_row = df_month[df_month["Regel"] == netto_key].iloc[0]
        total_actual = net_row["Actual maand"]
        total_budget = net_row["Budget maand"]
        total_actual_ytd = net_row["Actual YTD"]
        total_budget_ytd = net_row["Budget YTD"]
    else:
        total_actual = df_month["Actual maand"].sum()
        total_budget = df_month["Budget maand"].sum()
        total_actual_ytd = df_month["Actual YTD"].sum()
        total_budget_ytd = df_month["Budget YTD"].sum()

    total_var = total_actual - total_budget
    total_var_ytd = total_actual_ytd - total_budget_ytd

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Actual maand", f"€{total_actual:,.0f}")
    m2.metric("Budget maand", f"€{total_budget:,.0f}")
    m3.metric("Variantie maand", f"€{total_var:,.0f}", delta=f"{(total_var / total_budget * 100):+.1f}%" if total_budget else None)
    m4.metric("Variantie YTD", f"€{total_var_ytd:,.0f}", delta=f"{(total_var_ytd / total_budget_ytd * 100):+.1f}%" if total_budget_ytd else None)

    st.dataframe(
        df_month.drop(columns=["_subtotal"]).style.format({
            "Actual maand": "€{:,.0f}",
            "Budget maand": "€{:,.0f}",
            "Variantie maand": "€{:,.0f}",
            "Variantie maand %": "{:+.1f}%",
            "Actual YTD": "€{:,.0f}",
            "Budget YTD": "€{:,.0f}",
            "Variantie YTD": "€{:,.0f}",
            "Variantie YTD %": "{:+.1f}%"
        }),
        use_container_width=True,
        hide_index=True
    )

    st.markdown("---")
    st.markdown("#### Variantiematrix per maand")
    matrix_rows = []
    for cat_key in get_sorted_report_categories(include_subtotals=True):
        row = {"Regel": REPORT_CATEGORIES[cat_key]["name"]}
        for m in range(1, 13):
            var_val = actual.get(cat_key, [0.0] * 12)[m - 1] - budget.get(cat_key, [0.0] * 12)[m - 1]
            row[MONTH_LABELS_NL[m]] = var_val
        matrix_rows.append(row)
    df_matrix = pd.DataFrame(matrix_rows)
    st.dataframe(
        df_matrix.style.format({MONTH_LABELS_NL[m]: "€{:,.0f}" for m in range(1, 13)}),
        use_container_width=True,
        hide_index=True
    )

    st.markdown("---")
    category_choice = st.selectbox(
        "Grafiek voor rapportregel",
        options=get_sorted_report_categories(include_subtotals=True),
        format_func=lambda k: REPORT_CATEGORIES[k]["name"],
        key="variance_graph_category",
    )
    graph_df = pd.DataFrame({
        "Maand": [MONTH_LABELS_NL[m] for m in range(1, 13)],
        "Actual": actual.get(category_choice, [0.0] * 12),
        "Budget": budget.get(category_choice, [0.0] * 12),
    })
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Budget", x=graph_df["Maand"], y=graph_df["Budget"], marker_color="#87CEEB"))
    fig.add_trace(go.Bar(name="Actual", x=graph_df["Maand"], y=graph_df["Actual"], marker_color="#1e3a5f"))
    fig.update_layout(
        barmode="group",
        height=380,
        title=f"Actual vs Budget — {REPORT_CATEGORIES[category_choice]['name']}"
    )
    st.plotly_chart(fig, use_container_width=True)

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
    # Compacte, consistente dashboard styling
    st.markdown("""
    <style>
    [data-testid="stSidebarContent"] [data-testid="stRadio"] > div:first-child {
        display: none;
    }
    [data-testid="stSidebarContent"] [data-testid="stRadio"] div[role="radiogroup"] {
        gap: 4px;
    }
    [data-testid="stSidebarContent"] [data-testid="stRadio"] label {
        padding: 8px 12px !important;
        border-radius: 8px !important;
        font-size: 0.93rem !important;
        font-weight: 500 !important;
    }
    [data-testid="stSidebarContent"] [data-testid="stRadio"] label:hover {
        background: rgba(49, 51, 63, 0.08) !important;
    }
    [data-testid="stVerticalBlock"] [data-testid="stExpander"] {
        border: 1px solid rgba(49, 51, 63, 0.12);
        border-radius: 8px;
    }
    .block-container {
        padding-top: 1.2rem;
    }
    </style>
    """, unsafe_allow_html=True)

    # =========================================================================
    # SIDEBAR – Configuratie & Navigatie
    # =========================================================================
    st.sidebar.markdown("**LAB Groep**")
    st.sidebar.markdown("Financial Dashboard", unsafe_allow_html=False)
    st.sidebar.caption("v18 — vereenvoudigde navigatie")

    # API Key input (alleen tonen als niet in secrets)
    api_from_secrets = False
    try:
        if st.secrets.get("ODOO_API_KEY", ""):
            api_from_secrets = True
    except:
        pass

    with st.sidebar.expander("🔐 API instellingen", expanded=not api_from_secrets):
        if not api_from_secrets:
            api_input = st.text_input(
                "Odoo API Key",
                value=st.session_state.get("api_key", ""),
                type="password",
                help="Voer je Odoo API key in",
                key="api_key_input"
            )
            if api_input:
                st.session_state.api_key = api_input

        openai_input = st.text_input(
            "OpenAI API Key",
            value=st.session_state.get("openai_key", ""),
            type="password",
            help="Voer je OpenAI API key in voor de AI Chat functie",
            key="openai_key_input"
        )
        if openai_input:
            st.session_state.openai_key = openai_input

    # Check of we een API key hebben
    if not get_api_key():
        st.warning("Voer je Odoo API Key in via de sidebar om te beginnen")
        st.stop()

    st.sidebar.markdown("---")

    # Navigatie
    NAV_ITEMS = [
        "Overzicht",
        "Bank",
        "Facturen",
        "Producten",
        "Klantenkaart",
        "Kosten",
        "Rapportage",
        "Balans",
        "AI Chat",
        "LAB Projects",
    ]
    NAV_LABELS = {
        "Overzicht": "📊 Overzicht",
        "Bank": "🏦 Bank",
        "Facturen": "🧾 Facturen",
        "Producten": "📦 Producten",
        "Klantenkaart": "🗺️ Klantenkaart",
        "Kosten": "💸 Kosten",
        "Rapportage": "🧮 Rapportage",
        "Balans": "⚖️ Balans",
        "AI Chat": "💬 AI Chat",
        "LAB Projects": "🧩 LAB Projects",
    }
    selected_nav = st.sidebar.radio(
        "Navigatie",
        NAV_ITEMS,
        label_visibility="collapsed",
        format_func=lambda item: NAV_LABELS.get(item, item)
    )

    # =========================================================================
    # FILTERS – Compacter in inklapbaar paneel
    # =========================================================================
    current_year = datetime.now().year
    years = list(range(current_year, 2022, -1))
    entity_options = ["Alle bedrijven"] + list(COMPANIES.values())

    with st.expander("🎛️ Dashboard filters", expanded=False):
        f_col1, f_col2, f_col3, f_col4 = st.columns([1, 1, 2, 1])
        with f_col1:
            selected_year = st.selectbox("Jaar", years, index=0, key="filter_year")
        with f_col2:
            selected_entity = st.selectbox("Entiteit", entity_options, key="filter_entity")
        with f_col3:
            if "exclude_intercompany" not in st.session_state:
                st.session_state.exclude_intercompany = False
            exclude_intercompany = st.checkbox(
                "Intercompany uitsluiten",
                value=st.session_state.exclude_intercompany,
                key="exclude_intercompany_checkbox",
                help="Sluit boekingen met andere LAB-entiteiten uit"
            )
            st.session_state.exclude_intercompany = exclude_intercompany
        with f_col4:
            st.caption(f"Update: {datetime.now().strftime('%H:%M')}")
            if st.button("Ververs", key="refresh_btn"):
                st.cache_data.clear()
                st.rerun()

    if "exclude_intercompany" not in st.session_state:
        st.session_state.exclude_intercompany = False

    selected_year = st.session_state.get("filter_year", current_year)
    selected_entity = st.session_state.get("filter_entity", entity_options[0])
    exclude_intercompany = st.session_state.get("exclude_intercompany", False)

    intercompany_label = "zonder intercompany" if exclude_intercompany else "incl. intercompany"
    st.caption(f"Actieve selectie: {selected_year} • {selected_entity} • {intercompany_label}")
    st.markdown("---")

    company_id = None
    if selected_entity != "Alle bedrijven":
        company_id = [k for k, v in COMPANIES.items() if v == selected_entity][0]

    # =========================================================================
    # NAVIGATIE – Pagina-inhoud op basis van selectie
    # =========================================================================
    
    # =========================================================================
    # PAGINA: OVERZICHT
    # =========================================================================
    if selected_nav == "Overzicht":
        st.header("Financieel Overzicht")
        
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
        st.subheader("Omzet Tijdlijn" + (" (excl. IC)" if exclude_intercompany else ""))
        
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
            st.caption("Kies 'Dag' voor detail • Gebruik de schuifbalk om te navigeren • Sleep de randen om in te zoomen")
        
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
        st.subheader("Omzet Week-op-Week: Vergelijking met Vorig Jaar" + (" (excl. IC)" if exclude_intercompany else ""))

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
    # PAGINA: BANK
    # =========================================================================
    elif selected_nav == "Bank":
        st.header("Banksaldi per Rekening")
        
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
                st.subheader("R/C Intercompany Posities")
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
                st.subheader("Verdeling per Entiteit")
                
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
    # PAGINA: FACTUREN
    # =========================================================================
    elif selected_nav == "Facturen":
        st.header("Facturen")
        
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
    # PAGINA: PRODUCTEN (met subtabs)
    # =========================================================================
    elif selected_nav == "Producten":
        st.header("Productanalyse")
        
        # Subtabs voor producten
        prod_subtabs = st.tabs(["📦 Productcategorieën", "🏅 Top Producten", "🎨 Verf vs Behang", "📊 Categorie Trend"])
        
        # Subtab 1: Productcategorieën
        with prod_subtabs[0]:
            st.subheader("Omzet per Productcategorie")
            
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
            st.subheader(f"Omzet per Categorie – Week Trend {selected_year}")

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
    # PAGINA: KLANTENKAART
    # =========================================================================
    elif selected_nav == "Klantenkaart":
        st.header("Klantenkaart LAB Projects")
        
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
                    st.subheader("Top 15 Klanten op Omzet")
                    
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
    # PAGINA: KOSTEN
    # =========================================================================
    elif selected_nav == "Kosten":
        st.header("Kostenanalyse")
        if exclude_intercompany:
            st.caption("Intercompany boekingen uitgesloten")
        
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
                st.subheader("Top 15 Kostenposten")
                top_costs = sorted_accounts[:15]
                df_top = pd.DataFrame(top_costs, columns=["Kostensoort", "Bedrag"])
                
                fig = px.bar(df_top, y="Kostensoort", x="Bedrag", orientation="h",
                            color_discrete_sequence=["#1e3a5f"])
                fig.update_layout(height=500, yaxis={'categoryorder': 'total ascending'})
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.subheader("Kostenverdeling")
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
    # PAGINA: RAPPORTAGE (MAPPING + BUDGET + VARIANTIE + BALANSSTRUCTUUR)
    # =========================================================================
    elif selected_nav == "Rapportage":
        st.header("Rapportage & Budget")

        scope_col1, scope_col2, scope_col3 = st.columns([1.3, 1.3, 2])
        with scope_col1:
            report_scope = st.radio(
                "Scope",
                ["Per bedrijf", "Geconsolideerd"],
                horizontal=True,
                key="report_scope_mode"
            )
        with scope_col2:
            if report_scope == "Per bedrijf":
                default_company_name = selected_entity if selected_entity != "Alle bedrijven" else list(COMPANIES.values())[0]
                company_name = st.selectbox(
                    "Bedrijf",
                    options=list(COMPANIES.values()),
                    index=list(COMPANIES.values()).index(default_company_name) if default_company_name in COMPANIES.values() else 0,
                    key="report_scope_company"
                )
                report_company_id = [cid for cid, cname in COMPANIES.items() if cname == company_name][0]
            else:
                st.caption("Consolidatie over alle bedrijven")
                report_company_id = None
        with scope_col3:
            report_exclude_ic = st.checkbox(
                "Intercompany elimineren (actuals)",
                value=True,
                key="report_exclude_ic",
                help="Sluit transacties met intercompany partners uit in de actuals."
            )

        tab_map, tab_budget, tab_variance, tab_balance_map, tab_balance_report = st.tabs([
            "🧭 Rekeningmapping W&V",
            "📥 Budget import",
            "📊 Variantie per maand",
            "🏛️ Balansmapping",
            "⚖️ Balansrapport (Activa/Passiva)"
        ])

        with tab_map:
            st.caption("Map rekeningen 1-op-1 naar rapportregels op geaggregeerd niveau.")
            render_draggable_mapping_tool(report_company_id, selected_year)

        with tab_budget:
            render_budget_import_tab(selected_year)

        with tab_variance:
            render_variance_analysis_tab(
                selected_year=selected_year,
                report_company_id=report_company_id,
                exclude_intercompany=report_exclude_ic
            )

        with tab_balance_map:
            render_balance_mapping_tool(report_company_id, selected_year)

        with tab_balance_report:
            balance_date_struct = st.date_input(
                "Peildatum balansrapport",
                value=datetime.now().date(),
                max_value=datetime.now().date(),
                key="balance_struct_date"
            )
            render_structured_balance_report(
                as_of_date=balance_date_struct,
                company_id=report_company_id,
                exclude_intercompany=report_exclude_ic
            )

    # =========================================================================
    # PAGINA: BALANS
    # =========================================================================
    elif selected_nav == "Balans":
        st.header("Balans (Kwadrant)")
        
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
    # PAGINA: AI CHAT
    # =========================================================================
    elif selected_nav == "AI Chat":
        st.header("AI Financial Assistant")
        
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
    # PAGINA: LAB PROJECTS
    # =========================================================================
    elif selected_nav == "LAB Projects":
        st.header("LAB Projects – Analytische Projectanalyse")

        # --- Laad analytische plannen ---
        with st.spinner("Analytische plannen ophalen..."):
            analytic_plans = get_analytic_plans()

        if not analytic_plans:
            st.warning(
                "Geen analytische plannen gevonden in Odoo. "
                "Controleer of de analytische boekhouding-module actief is."
            )
        else:
            plan_options = {p["name"]: p["id"] for p in sorted(analytic_plans, key=lambda x: x["name"])}

            top_c1, top_c2 = st.columns([1, 3])
            with top_c1:
                selected_plan_name = st.selectbox(
                    "Analytisch Plan",
                    list(plan_options.keys()),
                    key="proj_plan_select",
                    help="Kies het analytische plan (bijv. Projecten)"
                )
            selected_plan_id = plan_options[selected_plan_name]

            with st.spinner(f"Projecten ophalen voor '{selected_plan_name}'..."):
                analytic_accounts = get_analytic_accounts(selected_plan_id)

            if not analytic_accounts:
                st.info(f"Geen analytische rekeningen gevonden onder plan '{selected_plan_name}'.")
            else:
                def _account_label(a):
                    code = a.get("code") or ""
                    name = a.get("name", "")
                    return f"{code} \u2013 {name}".strip("\u2013 ") if code else name

                account_label_to_id = {
                    _account_label(a): a["id"]
                    for a in sorted(analytic_accounts, key=lambda x: x.get("name", ""))
                }

                with top_c2:
                    selected_project_labels = st.multiselect(
                        "Project(en) — leeg = overzicht alle projecten",
                        list(account_label_to_id.keys()),
                        key="proj_multiselect",
                        help="Selecteer één of meerdere projecten voor gecombineerde detailanalyse"
                    )

                st.markdown("---")

                # ================================================================
                # SECTIE 1: PORTEFEUILLE OVERZICHT (altijd zichtbaar)
                # ================================================================
                st.subheader(f"Portefeuille – {selected_plan_name}")

                with st.spinner("Alle projecten laden..."):
                    all_summaries = get_all_analytic_summaries(selected_plan_id)

                if not all_summaries:
                    st.info("Geen projectdata gevonden voor dit plan.")
                else:
                    def _classify(row):
                        if row["Opbrengst"] <= 0:
                            return "Geen omzet"
                        elif row["Resultaat"] < 0:
                            return "Verlieslatend"
                        elif (row["Marge %"] or 0) < 10:
                            return "Break-even (0\u201310%)"
                        elif (row["Marge %"] or 0) < 25:
                            return "Winstgevend (10\u201325%)"
                        else:
                            return "Uitstekend (>25%)"

                    df_all = pd.DataFrame(all_summaries)
                    df_all["Cluster"] = df_all.apply(_classify, axis=1)

                    totals_rev = df_all["Opbrengst"].sum()
                    totals_res = df_all["Resultaat"].sum()
                    neg_count  = len(df_all[df_all["Resultaat"] < 0])

                    pk1, pk2, pk3, pk4 = st.columns(4)
                    pk1.metric("Projecten", str(len(df_all)))
                    pk2.metric("Totaal Opbrengst", f"\u20ac{totals_rev:,.0f}")
                    pk3.metric("Totaal Resultaat", f"\u20ac{totals_res:,.0f}",
                               delta="positief" if totals_res >= 0 else "negatief",
                               delta_color="normal" if totals_res >= 0 else "inverse")
                    pk4.metric("Verlieslatend", str(neg_count),
                               delta=f"{neg_count / len(df_all) * 100:.0f}% van totaal",
                               delta_color="inverse" if neg_count > 0 else "off")

                    st.markdown("---")

                    CLUSTER_COLORS = {
                        "Verlieslatend":          "#c0392b",
                        "Break-even (0\u201310%)":  "#f39c12",
                        "Winstgevend (10\u201325%)": "#27ae60",
                        "Uitstekend (>25%)":       "#1a5276",
                        "Geen omzet":              "#7f8c8d",
                    }
                    df_bubble = df_all.copy()
                    df_bubble["Marge_disp"] = df_bubble["Marge %"].fillna(0)
                    df_bubble["Bubble"]     = df_bubble["Resultaat"].abs().clip(lower=200)

                    fig_bubble = px.scatter(
                        df_bubble,
                        x="Opbrengst", y="Marge_disp",
                        size="Bubble", color="Cluster",
                        color_discrete_map=CLUSTER_COLORS,
                        hover_name="Project",
                        hover_data={
                            "Opbrengst":  ":\u20ac,.0f",
                            "Kosten":     ":\u20ac,.0f",
                            "Resultaat":  ":\u20ac,.0f",
                            "Marge_disp": ":.1f",
                            "Bubble":     False,
                        },
                        title="Projectportfolio: Opbrengst vs Marge % (grootte = |resultaat|)",
                        labels={"Opbrengst": "Opbrengst (\u20ac)", "Marge_disp": "Marge %",
                                "Cluster": "Categorie"},
                        height=420,
                    )
                    fig_bubble.add_hline(y=0,  line_color="#c0392b", line_dash="dot",
                                         annotation_text="0% (break-even)")
                    fig_bubble.add_hline(y=10, line_color="#f39c12", line_dash="dash",
                                         annotation_text="10%")
                    fig_bubble.add_hline(y=25, line_color="#27ae60", line_dash="dash",
                                         annotation_text="25%")
                    st.plotly_chart(fig_bubble, use_container_width=True)

                    CLUSTER_ORDER = [
                        "Verlieslatend",
                        "Break-even (0\u201310%)",
                        "Winstgevend (10\u201325%)",
                        "Uitstekend (>25%)",
                        "Geen omzet",
                    ]

                    def _cell_color(val):
                        if isinstance(val, (int, float)) and val < 0:
                            return "color: #c0392b; font-weight: bold"
                        return ""

                    for cl in CLUSTER_ORDER:
                        cl_df = df_all[df_all["Cluster"] == cl].sort_values("Resultaat")
                        if cl_df.empty:
                            continue
                        n   = len(cl_df)
                        tot = cl_df["Resultaat"].sum()
                        exp_label = (
                            f"{cl}  \u2013  {n} project{'en' if n != 1 else ''}  \u00b7  "
                            f"resultaat \u20ac{tot:,.0f}"
                        )
                        with st.expander(exp_label, expanded=(cl == "Verlieslatend" and n > 0)):
                            disp = cl_df[["Project", "Opbrengst", "Kosten",
                                          "Resultaat", "Marge %"]].copy()
                            st.dataframe(
                                disp.style
                                .format({
                                    "Opbrengst": "\u20ac{:,.0f}",
                                    "Kosten":    "\u20ac{:,.0f}",
                                    "Resultaat": "\u20ac{:,.0f}",
                                    "Marge %": lambda v: f"{v:.1f}%" if v is not None else "\u2013",
                                })
                                .applymap(_cell_color, subset=["Resultaat"]),
                                use_container_width=True, hide_index=True,
                            )

                    # AI-analyse verlieslatende projecten
                    st.markdown("---")
                    neg_projects = [s for s in all_summaries if s.get("Resultaat", 0) < 0]

                    if not neg_projects:
                        st.success(
                            "Geen verlieslatende projecten gevonden \u2013 "
                            "alle projecten zijn winstgevend of break-even."
                        )
                    else:
                        st.warning(
                            f"{len(neg_projects)} project(en) met negatief resultaat. "
                            "Klik op de knop hieronder voor een AI-analyse."
                        )
                        if not get_openai_key():
                            st.info(
                                "Voer een OpenAI API key in via de sidebar "
                                "om de AI-analyse te activeren."
                            )
                        else:
                            if st.button(
                                "Start AI-analyse verlieslatende projecten",
                                key="proj_ai_analyse_btn",
                                type="primary",
                            ):
                                project_lines = []
                                for s in sorted(neg_projects, key=lambda x: x["Resultaat"]):
                                    marge_str = (
                                        f"{s['Marge %']:.1f}%"
                                        if s.get("Marge %") is not None else "geen omzet"
                                    )
                                    project_lines.append(
                                        f"- **{s['Project']}**: "
                                        f"Opbrengst \u20ac{s['Opbrengst']:,.0f} | "
                                        f"Kosten \u20ac{s['Kosten']:,.0f} | "
                                        f"Resultaat \u20ac{s['Resultaat']:,.0f} | "
                                        f"Marge {marge_str}"
                                    )
                                project_context = "\n".join(project_lines)

                                pos_projects = [
                                    s for s in all_summaries if s.get("Resultaat", 0) >= 0
                                ]
                                valid_pos = [s for s in pos_projects if s.get("Marge %")]
                                benchmark_str = (
                                    f"Ter referentie: de {len(pos_projects)} winstgevende "
                                    f"projecten hebben een gemiddelde marge van "
                                    f"{sum(s['Marge %'] for s in valid_pos) / len(valid_pos):.1f}%."
                                    if valid_pos else ""
                                )

                                messages = [
                                    {
                                        "role": "system",
                                        "content": (
                                            "Je bent een ervaren financieel controller voor LAB Groep, "
                                            "een bedrijf dat projecten uitvoert op het gebied van "
                                            "verf en behang. Je analyseert projectmarges en geeft "
                                            "concrete, praktische aanbevelingen in het Nederlands. "
                                            "Wees specifiek en actionable."
                                        ),
                                    },
                                    {
                                        "role": "user",
                                        "content": (
                                            f"Analyseer de volgende {len(neg_projects)} verlieslatende "
                                            f"projecten uit het analytische plan '{selected_plan_name}':"
                                            f"\n\n{project_context}\n\n{benchmark_str}\n\n"
                                            "Geef per project:\n"
                                            "1. De meest waarschijnlijke oorzaak van het verlies\n"
                                            "2. Concrete actie(s) om de marge te verbeteren\n"
                                            "3. Urgentiescore: Kritiek (>\u20ac5k verlies) / Hoog / Gemiddeld\n\n"
                                            "Sluit af met:\n"
                                            "- Een prioriteitenlijst (welk project eerst aanpakken)\n"
                                            "- Structurele aanbevelingen om margerisico te voorkomen"
                                        ),
                                    },
                                ]

                                with st.spinner("AI analyseert de verlieslatende projecten..."):
                                    ai_response, ai_error = call_openai(
                                        messages, model="gpt-4o-mini"
                                    )

                                if ai_error:
                                    st.error(f"AI-fout: {ai_error}")
                                elif ai_response:
                                    st.markdown(ai_response)

                # ================================================================
                # SECTIE 2: FACTUREN OVERZICHT (alle projecten in plan)
                # ================================================================
                st.markdown("---")
                _fov_title = (
                    f"Facturen – {len(selected_project_labels)} project{'en' if len(selected_project_labels) != 1 else ''} geselecteerd"
                    if selected_project_labels
                    else "Facturen – Overzicht alle projecten"
                )
                st.subheader(_fov_title)

                if st.session_state.get("_fov_plan_id") != selected_plan_id:
                    st.session_state["_fov_loaded"] = False
                    st.session_state["_fov_data"] = []
                    st.session_state["_fov_plan_id"] = selected_plan_id

                # Reset cache als projectselectie is gewijzigd
                _fov_proj_key = tuple(sorted(selected_project_labels))
                if st.session_state.get("_fov_proj_key") != _fov_proj_key:
                    st.session_state["_fov_loaded"] = False
                    st.session_state["_fov_data"] = []
                    st.session_state["_fov_proj_key"] = _fov_proj_key

                _PAYMENT_LABELS_FOV = {
                    "not_paid":   "Niet betaald",
                    "partial":    "Deels betaald",
                    "paid":       "Betaald",
                    "reversed":   "Teruggedraaid",
                    "in_payment": "In verwerking",
                }

                # Bepaal welke accounts geladen worden op basis van selectie
                _fov_accounts = (
                    [a for a in analytic_accounts
                     if _account_label(a) in selected_project_labels]
                    if selected_project_labels
                    else analytic_accounts
                )
                _fov_btn_label = (
                    f"Facturen ophalen voor {len(_fov_accounts)} geselecteerd project{'en' if len(_fov_accounts) != 1 else ''}"
                    if selected_project_labels
                    else "Facturen ophalen voor alle projecten"
                )

                if not st.session_state.get("_fov_loaded"):
                    st.info(
                        "Klik op de knop hieronder om de facturen op te halen. "
                        "Dit kan even duren afhankelijk van het aantal projecten."
                    )
                    if st.button(_fov_btn_label, key="btn_fov_load"):
                        _collected_inv = []
                        with st.spinner(
                            f"Facturen ophalen voor {len(_fov_accounts)} project{'en' if len(_fov_accounts) != 1 else ''}..."
                        ):
                            for _acc in _fov_accounts:
                                _acc_inv = get_analytic_invoices_with_share(_acc["id"])
                                _acc_lbl = _account_label(_acc)
                                for _inv in _acc_inv:
                                    _collected_inv.append(
                                        {
                                            "Project":           _acc_lbl,
                                            "Type": (
                                                "Verkoop"
                                                if _inv.get("move_type")
                                                in ("out_invoice", "out_refund")
                                                else "Inkoop"
                                            ),
                                            "Factuurnr":         _inv.get("name", ""),
                                            "Datum":             _inv.get("invoice_date", ""),
                                            "Relatie": (
                                                _inv["partner_id"][1]
                                                if _inv.get("partner_id")
                                                else ""
                                            ),
                                            "Totaal excl. BTW":  _inv.get("amount_untaxed", 0),
                                            "% Project":         _inv.get("proj_share_pct", 100),
                                            "Aandeel excl. BTW": _inv.get("proj_share_untaxed", _inv.get("amount_untaxed", 0)),
                                            "Openstaand":        _inv.get("proj_share_residual", _inv.get("amount_residual", 0)),
                                            "Status": _PAYMENT_LABELS_FOV.get(
                                                _inv.get("payment_state", ""),
                                                _inv.get("payment_state", ""),
                                            ),
                                        }
                                    )
                        st.session_state["_fov_data"] = _collected_inv
                        st.session_state["_fov_loaded"] = True
                        st.rerun()
                else:
                    _fov_rows = st.session_state["_fov_data"]
                    _fov_refresh_col, _ = st.columns([1, 5])
                    with _fov_refresh_col:
                        if st.button("Verversen", key="btn_fov_refresh"):
                            st.session_state["_fov_loaded"] = False
                            st.rerun()
                    if not _fov_rows:
                        st.info("Geen facturen gevonden voor projecten in dit plan.")
                    else:
                        _df_fov = pd.DataFrame(_fov_rows)
                        _fov_f1, _fov_f2 = st.columns(2)
                        with _fov_f1:
                            _fov_type = st.selectbox(
                                "Type",
                                ["Alle", "Verkoop", "Inkoop"],
                                key="fov_type_sel",
                            )
                        with _fov_f2:
                            _fov_status = st.selectbox(
                                "Status",
                                ["Alle", "Niet betaald", "Deels betaald", "Betaald"],
                                key="fov_status_sel",
                            )
                        _df_fov_show = _df_fov.copy()
                        if _fov_type != "Alle":
                            _df_fov_show = _df_fov_show[_df_fov_show["Type"] == _fov_type]
                        if _fov_status != "Alle":
                            _df_fov_show = _df_fov_show[_df_fov_show["Status"] == _fov_status]
                        _fov_k1, _fov_k2, _fov_k3 = st.columns(3)
                        _fov_k1.metric("Facturen", str(len(_df_fov_show)))
                        _fov_k2.metric(
                            "Aandeel excl. BTW",
                            f"\u20ac{_df_fov_show['Aandeel excl. BTW'].sum():,.0f}",
                        )
                        _fov_k3.metric(
                            "Openstaand (aandeel)",
                            f"\u20ac{_df_fov_show['Openstaand'].sum():,.0f}",
                            delta_color=(
                                "inverse"
                                if _df_fov_show["Openstaand"].sum() > 0
                                else "off"
                            ),
                        )
                        st.dataframe(
                            _df_fov_show.style.format(
                                {
                                    "Totaal excl. BTW":  "\u20ac{:,.2f}",
                                    "% Project":         "{:.1f}%",
                                    "Aandeel excl. BTW": "\u20ac{:,.2f}",
                                    "Openstaand":        "\u20ac{:,.2f}",
                                }
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                        _csv_fov = _df_fov_show.to_csv(index=False).encode("utf-8")
                        st.download_button(
                            "Download CSV",
                            data=_csv_fov,
                            file_name=f"facturen_{selected_plan_name}.csv",
                            mime="text/csv",
                            key="dl_fov",
                        )

                # ================================================================
                # SECTIE 3: PROJECTDETAIL (alleen als projecten geselecteerd)
                # ================================================================
                if selected_project_labels:
                    st.markdown("---")
                    st.subheader(
                        f"Projectdetail \u2013 {len(selected_project_labels)} "
                        f"project{'en' if len(selected_project_labels) != 1 else ''} geselecteerd"
                    )

                    PAYMENT_LABELS_P = {
                        "not_paid":   "Niet betaald",
                        "partial":    "Deels betaald",
                        "paid":       "Betaald",
                        "reversed":   "Teruggedraaid",
                        "in_payment": "In verwerking",
                    }

                    for proj_label in selected_project_labels:
                        proj_account_id = account_label_to_id[proj_label]

                        with st.expander(f"**{proj_label}**", expanded=True):

                            # Marge KPIs
                            with st.spinner(f"Boekingsdata laden..."):
                                alines = get_analytic_lines(proj_account_id)

                            if alines:
                                p_revenue = sum(l.get("amount", 0) for l in alines
                                                if (l.get("amount") or 0) > 0)
                                p_costs   = abs(sum(l.get("amount", 0) for l in alines
                                                    if (l.get("amount") or 0) < 0))
                                p_result  = p_revenue - p_costs
                                p_margin  = p_result / p_revenue * 100 if p_revenue else 0
                                p_dates   = sorted(l["date"] for l in alines if l.get("date"))

                                kc1, kc2, kc3, kc4 = st.columns(4)
                                kc1.metric("Opbrengsten",    f"\u20ac{p_revenue:,.0f}")
                                kc2.metric("Kosten",         f"\u20ac{p_costs:,.0f}")
                                kc3.metric("Resultaat",      f"\u20ac{p_result:,.0f}",
                                           delta=f"{p_margin:.1f}% marge",
                                           delta_color="normal" if p_result >= 0 else "inverse")
                                kc4.metric("Boekingsregels", str(len(alines)))
                                if p_dates:
                                    st.caption(
                                        f"Eerste boeking: {p_dates[0]} \u00b7 "
                                        f"Laatste boeking: {p_dates[-1]}"
                                    )
                            else:
                                st.info("Geen analytische boekingen gevonden voor dit project.")

                            st.markdown("---")

                            # Facturen in/uit
                            with st.spinner("Facturen laden..."):
                                all_inv = get_analytic_invoices_with_share(proj_account_id)

                            if not all_inv:
                                st.info(
                                    "Geen facturen gevonden. Controleer of factuurregels "
                                    "analytisch zijn toegewezen aan dit project."
                                )
                            else:
                                out_inv = sorted(
                                    [i for i in all_inv if i.get("move_type")
                                     in ("out_invoice", "out_refund")],
                                    key=lambda x: x.get("invoice_date", ""), reverse=True
                                )
                                in_inv = sorted(
                                    [i for i in all_inv if i.get("move_type")
                                     in ("in_invoice", "in_refund")],
                                    key=lambda x: x.get("invoice_date", ""), reverse=True
                                )

                                def _inv_row_p(i):
                                    return {
                                        "Factuurnr":          i.get("name", ""),
                                        "Datum":              i.get("invoice_date", ""),
                                        "Relatie":            i["partner_id"][1] if i.get("partner_id") else "",
                                        "Totaal excl. BTW":   i.get("amount_untaxed", 0),
                                        "% Project":          i.get("proj_share_pct", 100),
                                        "Aandeel excl. BTW":  i.get("proj_share_untaxed", i.get("amount_untaxed", 0)),
                                        "Aandeel openstaand": i.get("proj_share_residual", i.get("amount_residual", 0)),
                                        "Status":             PAYMENT_LABELS_P.get(
                                            i.get("payment_state", ""), i.get("payment_state", "")
                                        ),
                                    }

                                _fmt_p = {
                                    "Totaal excl. BTW":   "\u20ac{:,.2f}",
                                    "% Project":          "{:.1f}%",
                                    "Aandeel excl. BTW":  "\u20ac{:,.2f}",
                                    "Aandeel openstaand": "\u20ac{:,.2f}",
                                }

                                col_out, col_in = st.columns(2)

                                with col_out:
                                    st.markdown(f"**Verkoopfacturen ({len(out_inv)})**")
                                    if out_inv:
                                        df_out_p = pd.DataFrame([_inv_row_p(i) for i in out_inv])
                                        st.metric(
                                            "Aandeel omzet",
                                            f"\u20ac{df_out_p['Aandeel excl. BTW'].sum():,.0f}",
                                            delta=(
                                                f"\u20ac{df_out_p['Aandeel openstaand'].sum():,.0f} open"
                                                if df_out_p["Aandeel openstaand"].sum() > 0 else None
                                            ),
                                            delta_color="inverse" if df_out_p["Aandeel openstaand"].sum() > 0 else "off",
                                        )
                                        st.dataframe(
                                            df_out_p.style.format(_fmt_p),
                                            use_container_width=True, hide_index=True,
                                        )
                                        csv_out = df_out_p.to_csv(index=False).encode("utf-8")
                                        st.download_button(
                                            "Download verkoop CSV",
                                            data=csv_out,
                                            file_name=f"verkoop_{proj_account_id}.csv",
                                            mime="text/csv",
                                            key=f"dl_out_{proj_account_id}",
                                        )
                                    else:
                                        st.info("Geen verkoopfacturen gevonden.")

                                with col_in:
                                    st.markdown(f"**Inkoopfacturen ({len(in_inv)})**")
                                    if in_inv:
                                        df_in_p = pd.DataFrame([_inv_row_p(i) for i in in_inv])
                                        st.metric(
                                            "Aandeel inkoop",
                                            f"\u20ac{df_in_p['Aandeel excl. BTW'].sum():,.0f}",
                                        )
                                        st.dataframe(
                                            df_in_p.style.format(_fmt_p),
                                            use_container_width=True, hide_index=True,
                                        )
                                        csv_in = df_in_p.to_csv(index=False).encode("utf-8")
                                        st.download_button(
                                            "Download inkoop CSV",
                                            data=csv_in,
                                            file_name=f"inkoop_{proj_account_id}.csv",
                                            mime="text/csv",
                                            key=f"dl_in_{proj_account_id}",
                                        )
                                    else:
                                        st.info("Geen inkoopfacturen gevonden.")


if __name__ == "__main__":
    main()
