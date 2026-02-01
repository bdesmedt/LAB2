"""
LAB Groep Financial Dashboard v13
=================================
Wijzigingen t.o.v. v12:
- 📋 NIEUW: Maandafsluiting Checklist tab (wachtwoord: controller)
  * Automatische Odoo checks voor maandafsluiting
  * Ongeboekte facturen detectie
  * Bank reconciliatie status
  * Intercompany saldo controle (moet €0 zijn)
  * BTW saldi overzicht
  * Vraagposten/tussenrekeningen check
  * Vervallen debiteuren/crediteuren analyse
  * 📊 W&V Anomalie detectie:
    - Vergelijking met vorige maand
    - Vergelijking met 12-maands gemiddelde
    - Drempels: >50% EN >€5.000 verschil
    - Drill-down per categorie
  * Handmatige checklist items met voortgangsindicator
  * Export functie voor rapportage (incl. anomalieën)

Eerdere features (v12):
- 🤖 AI Chatbot met OpenAI Function Calling
- AI kiest automatisch de juiste Odoo queries
- 7 gespecialiseerde functies voor data ophalen

Eerdere features (v11 en eerder):
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
from typing import Optional, List, Dict, Any, Tuple

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
Je hebt toegang tot functies om Odoo data op te halen. Gebruik ALTIJD de beschikbare functies om data op te halen - maak geen aannames.

BEDRIJVEN:
- 1: LAB Shops (retail)
- 2: LAB Projects (projecten/behang/verf)
- 3: LAB Holding (holding)
- 4: Verf en Wand (verf specialist)
- 5: Vestingh Art of Living (premium interieur)

BELANGRIJKE REGELS:
1. Gebruik ALTIJD functies voor data - gok niet
2. Voor factuurvragen: gebruik search_invoices of get_partner_totals
3. Voor omzet/kosten: gebruik get_revenue_costs
4. Voor partners zoeken: gebruik search_partners
5. Bedragen in Euro's (€1.234,56)
6. Antwoord in het Nederlands"""

# Function definitions voor OpenAI
ODOO_FUNCTIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_invoices",
            "description": "Zoek facturen in Odoo. Gebruik voor: factuurtotalen, openstaande facturen, facturen per leverancier/klant.",
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_type": {
                        "type": "string",
                        "enum": ["in_invoice", "out_invoice", "in_refund", "out_refund", "all"],
                        "description": "Type factuur: in_invoice=inkoop/leverancier, out_invoice=verkoop/klant, in_refund=creditnota leverancier, out_refund=creditnota klant, all=alle facturen"
                    },
                    "partner_name": {
                        "type": "string",
                        "description": "Naam (of deel van naam) van klant/leverancier om op te filteren"
                    },
                    "partner_id": {
                        "type": "integer",
                        "description": "Specifiek partner ID om op te filteren"
                    },
                    "payment_state": {
                        "type": "string",
                        "enum": ["paid", "not_paid", "partial", "all"],
                        "description": "Betalingsstatus: paid=betaald, not_paid=onbetaald, partial=deels betaald, all=alles"
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Startdatum (YYYY-MM-DD)"
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Einddatum (YYYY-MM-DD)"
                    },
                    "company_id": {
                        "type": "integer",
                        "description": "Filter op specifiek bedrijf (1-5)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum aantal resultaten (default 50)"
                    }
                },
                "required": ["invoice_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_partner_totals",
            "description": "Haal totalen per partner op (klanten of leveranciers). Gebruik voor: top klanten, top leveranciers, totaal gefactureerd per partner.",
            "parameters": {
                "type": "object",
                "properties": {
                    "partner_type": {
                        "type": "string",
                        "enum": ["customer", "supplier"],
                        "description": "Type partner: customer=klanten (verkoopfacturen), supplier=leveranciers (inkoopfacturen)"
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Startdatum (YYYY-MM-DD)"
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Einddatum (YYYY-MM-DD)"
                    },
                    "company_id": {
                        "type": "integer",
                        "description": "Filter op specifiek bedrijf (1-5)"
                    },
                    "exclude_intercompany": {
                        "type": "boolean",
                        "description": "Sluit intercompany transacties uit (default true)"
                    },
                    "top_n": {
                        "type": "integer",
                        "description": "Aantal top partners om te tonen (default 10)"
                    }
                },
                "required": ["partner_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_revenue_costs",
            "description": "Haal omzet en/of kosten op, optioneel gegroepeerd per periode of categorie.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data_type": {
                        "type": "string",
                        "enum": ["revenue", "costs", "both"],
                        "description": "Type data: revenue=omzet (8xxx rekeningen), costs=kosten (4xxx/6xxx/7xxx), both=beide"
                    },
                    "group_by": {
                        "type": "string",
                        "enum": ["month", "quarter", "year", "account", "partner", "none"],
                        "description": "Groepering: month=per maand, quarter=per kwartaal, year=per jaar, account=per rekening, partner=per klant/leverancier, none=totaal"
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Startdatum (YYYY-MM-DD)"
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Einddatum (YYYY-MM-DD)"
                    },
                    "company_id": {
                        "type": "integer",
                        "description": "Filter op specifiek bedrijf (1-5)"
                    },
                    "exclude_intercompany": {
                        "type": "boolean",
                        "description": "Sluit intercompany transacties uit (default true)"
                    }
                },
                "required": ["data_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_partners",
            "description": "Zoek klanten of leveranciers op naam. Gebruik ook om partner_id te vinden voor andere queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_term": {
                        "type": "string",
                        "description": "Zoekterm (naam of deel van naam)"
                    },
                    "partner_type": {
                        "type": "string",
                        "enum": ["customer", "supplier", "all"],
                        "description": "Type partner: customer=klanten, supplier=leveranciers, all=beide"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum aantal resultaten (default 20)"
                    }
                },
                "required": ["search_term"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_account_balance",
            "description": "Haal het saldo van specifieke grootboekrekeningen op.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_code": {
                        "type": "string",
                        "description": "Rekeningcode (bijv. '8000') of prefix (bijv. '8' voor alle 8xxx rekeningen)"
                    },
                    "date_from": {
                        "type": "string",
                        "description": "Startdatum (YYYY-MM-DD)"
                    },
                    "date_to": {
                        "type": "string",
                        "description": "Einddatum (YYYY-MM-DD)"
                    },
                    "company_id": {
                        "type": "integer",
                        "description": "Filter op specifiek bedrijf (1-5)"
                    }
                },
                "required": ["account_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_open_items",
            "description": "Haal openstaande posten op (onbetaalde facturen).",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_type": {
                        "type": "string",
                        "enum": ["receivable", "payable", "both"],
                        "description": "Type: receivable=te ontvangen (debiteuren), payable=te betalen (crediteuren), both=beide"
                    },
                    "partner_name": {
                        "type": "string",
                        "description": "Filter op partner naam"
                    },
                    "company_id": {
                        "type": "integer",
                        "description": "Filter op specifiek bedrijf (1-5)"
                    },
                    "days_overdue": {
                        "type": "integer",
                        "description": "Alleen items die meer dan X dagen over de vervaldatum zijn"
                    }
                },
                "required": ["item_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_bank_balance",
            "description": "Haal actuele banksaldi op.",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_id": {
                        "type": "integer",
                        "description": "Filter op specifiek bedrijf (1-5), leeg voor alle bedrijven"
                    }
                },
                "required": []
            }
        }
    }
]

# Intercompany partner IDs
INTERCOMPANY_PARTNERS = [1, 2, 3, 4, 23, 24, 4509, 20618, 74170, 79863]

def get_openai_key():
    """Haal OpenAI API key op"""
    return st.session_state.get("openai_key", "")

def call_openai_with_functions(messages, functions=None):
    """Roep OpenAI API aan met function calling"""
    api_key = get_openai_key()
    if not api_key:
        return None, "Geen OpenAI API key geconfigureerd"
    
    try:
        payload = {
            "model": "gpt-4o-mini",
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 2000
        }
        
        if functions:
            payload["tools"] = functions
            payload["tool_choice"] = "auto"
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"], None
        else:
            return None, f"OpenAI error: {response.status_code} - {response.text}"
    except Exception as e:
        return None, f"OpenAI connection error: {e}"

# === FUNCTION IMPLEMENTATIES ===

def fn_search_invoices(invoice_type, partner_name=None, partner_id=None, payment_state="all", 
                       date_from=None, date_to=None, company_id=None, limit=50):
    """Zoek facturen"""
    domain = [["state", "=", "posted"]]
    
    # Invoice type filter
    if invoice_type != "all":
        domain.append(["move_type", "=", invoice_type])
    else:
        domain.append(["move_type", "in", ["in_invoice", "out_invoice", "in_refund", "out_refund"]])
    
    # Partner filter
    if partner_id:
        domain.append(["partner_id", "=", partner_id])
    elif partner_name:
        # Zoek eerst de partner
        partners = odoo_call("res.partner", "search_read", 
                            [["name", "ilike", partner_name], ["active", "in", [True, False]]],
                            ["id", "name"], limit=10)
        if partners:
            partner_ids = [p["id"] for p in partners]
            domain.append(["partner_id", "in", partner_ids])
    
    # Payment state filter
    if payment_state != "all":
        domain.append(["payment_state", "=", payment_state])
    
    # Date filters
    if date_from:
        domain.append(["invoice_date", ">=", date_from])
    if date_to:
        domain.append(["invoice_date", "<=", date_to])
    
    # Company filter
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    invoices = odoo_call("account.move", "search_read", domain,
                        ["name", "partner_id", "invoice_date", "amount_total", "amount_untaxed", 
                         "payment_state", "move_type", "company_id"],
                        limit=limit)
    
    # Bereken totalen
    total_amount = sum(inv.get("amount_total", 0) or 0 for inv in invoices)
    
    return {
        "count": len(invoices),
        "total_amount": total_amount,
        "invoices": invoices[:20],  # Beperk details voor context
        "note": f"Gevonden: {len(invoices)} facturen, totaal €{total_amount:,.2f}"
    }

def fn_get_partner_totals(partner_type, date_from=None, date_to=None, company_id=None, 
                          exclude_intercompany=True, top_n=10):
    """Haal totalen per partner op"""
    move_type = "out_invoice" if partner_type == "customer" else "in_invoice"
    
    domain = [["state", "=", "posted"], ["move_type", "=", move_type]]
    
    if date_from:
        domain.append(["invoice_date", ">=", date_from])
    if date_to:
        domain.append(["invoice_date", "<=", date_to])
    if company_id:
        domain.append(["company_id", "=", company_id])
    if exclude_intercompany:
        domain.append(["partner_id", "not in", INTERCOMPANY_PARTNERS])
    
    # Gebruik read_group voor aggregatie
    results = odoo_read_group("account.move", domain, 
                              ["amount_total:sum", "partner_id"],
                              ["partner_id"])
    
    # Sorteer en beperk
    sorted_results = sorted(results, key=lambda x: x.get("amount_total", 0) or 0, reverse=True)[:top_n]
    
    return {
        "partner_type": partner_type,
        "top_partners": sorted_results,
        "total_all": sum(r.get("amount_total", 0) or 0 for r in results),
        "count_partners": len(results)
    }

def fn_get_revenue_costs(data_type, group_by="none", date_from=None, date_to=None, 
                         company_id=None, exclude_intercompany=True):
    """Haal omzet en/of kosten op"""
    results = {}
    
    base_domain = [["parent_state", "=", "posted"]]
    if date_from:
        base_domain.append(["date", ">=", date_from])
    if date_to:
        base_domain.append(["date", "<=", date_to])
    if company_id:
        base_domain.append(["company_id", "=", company_id])
    if exclude_intercompany:
        base_domain.append(["partner_id", "not in", INTERCOMPANY_PARTNERS])
    
    # Bepaal groupby veld
    groupby_field = {
        "month": "date:month",
        "quarter": "date:quarter", 
        "year": "date:year",
        "account": "account_id",
        "partner": "partner_id",
        "none": None
    }.get(group_by)
    
    if data_type in ["revenue", "both"]:
        rev_domain = base_domain + [["account_id.code", "=like", "8%"]]
        if groupby_field:
            rev_data = odoo_read_group("account.move.line", rev_domain,
                                       ["credit:sum", "debit:sum"], [groupby_field])
        else:
            rev_data = odoo_read_group("account.move.line", rev_domain,
                                       ["credit:sum", "debit:sum"], [])
        # Omzet = credit - debit op 8xxx rekeningen
        for item in rev_data:
            item["revenue"] = (item.get("credit", 0) or 0) - (item.get("debit", 0) or 0)
        results["revenue"] = rev_data
    
    if data_type in ["costs", "both"]:
        cost_domain = base_domain + [["account_id.code", "=like", "4%"]]
        cost_domain_6 = base_domain + [["account_id.code", "=like", "6%"]]
        cost_domain_7 = base_domain + [["account_id.code", "=like", "7%"]]
        
        if groupby_field:
            cost_data_4 = odoo_read_group("account.move.line", cost_domain,
                                          ["debit:sum", "credit:sum"], [groupby_field])
            cost_data_6 = odoo_read_group("account.move.line", cost_domain_6,
                                          ["debit:sum", "credit:sum"], [groupby_field])
            cost_data_7 = odoo_read_group("account.move.line", cost_domain_7,
                                          ["debit:sum", "credit:sum"], [groupby_field])
        else:
            cost_data_4 = odoo_read_group("account.move.line", cost_domain,
                                          ["debit:sum", "credit:sum"], [])
            cost_data_6 = odoo_read_group("account.move.line", cost_domain_6,
                                          ["debit:sum", "credit:sum"], [])
            cost_data_7 = odoo_read_group("account.move.line", cost_domain_7,
                                          ["debit:sum", "credit:sum"], [])
        
        # Kosten = debit - credit
        all_costs = cost_data_4 + cost_data_6 + cost_data_7
        for item in all_costs:
            item["costs"] = (item.get("debit", 0) or 0) - (item.get("credit", 0) or 0)
        results["costs"] = all_costs
    
    return results

def fn_search_partners(search_term, partner_type="all", limit=20):
    """Zoek partners"""
    domain = [["name", "ilike", search_term], ["active", "in", [True, False]]]
    
    if partner_type == "customer":
        domain.append(["customer_rank", ">", 0])
    elif partner_type == "supplier":
        domain.append(["supplier_rank", ">", 0])
    
    partners = odoo_call("res.partner", "search_read", domain,
                        ["id", "name", "email", "phone", "customer_rank", "supplier_rank", "company_id"],
                        limit=limit)
    
    return {
        "count": len(partners),
        "partners": partners
    }

def fn_get_account_balance(account_code, date_from=None, date_to=None, company_id=None):
    """Haal saldo van rekeningen op"""
    domain = [["parent_state", "=", "posted"]]
    
    if len(account_code) < 4:
        domain.append(["account_id.code", "=like", f"{account_code}%"])
    else:
        domain.append(["account_id.code", "=", account_code])
    
    if date_from:
        domain.append(["date", ">=", date_from])
    if date_to:
        domain.append(["date", "<=", date_to])
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    results = odoo_read_group("account.move.line", domain,
                              ["debit:sum", "credit:sum", "account_id"],
                              ["account_id"])
    
    for item in results:
        item["balance"] = (item.get("debit", 0) or 0) - (item.get("credit", 0) or 0)
    
    total_balance = sum(r.get("balance", 0) for r in results)
    
    return {
        "account_code_filter": account_code,
        "accounts": results,
        "total_balance": total_balance
    }

def fn_get_open_items(item_type, partner_name=None, company_id=None, days_overdue=None):
    """Haal openstaande posten op"""
    from datetime import datetime, timedelta
    
    move_types = {
        "receivable": ["out_invoice"],
        "payable": ["in_invoice"],
        "both": ["in_invoice", "out_invoice"]
    }[item_type]
    
    domain = [
        ["state", "=", "posted"],
        ["move_type", "in", move_types],
        ["payment_state", "in", ["not_paid", "partial"]]
    ]
    
    if partner_name:
        partners = odoo_call("res.partner", "search_read",
                            [["name", "ilike", partner_name], ["active", "in", [True, False]]],
                            ["id"], limit=10)
        if partners:
            domain.append(["partner_id", "in", [p["id"] for p in partners]])
    
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    if days_overdue:
        cutoff_date = (datetime.now() - timedelta(days=days_overdue)).strftime("%Y-%m-%d")
        domain.append(["invoice_date_due", "<", cutoff_date])
    
    items = odoo_call("account.move", "search_read", domain,
                     ["name", "partner_id", "invoice_date", "invoice_date_due", 
                      "amount_total", "amount_residual", "move_type", "company_id"],
                     limit=100)
    
    total_open = sum(item.get("amount_residual", 0) or 0 for item in items)
    
    return {
        "item_type": item_type,
        "count": len(items),
        "total_open": total_open,
        "items": items[:30]
    }

def fn_get_bank_balance(company_id=None):
    """Haal banksaldi op"""
    domain = [["type", "=", "bank"]]
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    journals = odoo_call("account.journal", "search_read", domain,
                        ["name", "company_id", "current_statement_balance", "code"])
    
    # Filter R/C rekeningen uit
    bank_only = [j for j in journals if "R/C" not in j.get("name", "") and "RC " not in j.get("name", "")]
    
    total = sum(j.get("current_statement_balance", 0) or 0 for j in bank_only)
    
    return {
        "banks": bank_only,
        "total_balance": total
    }

# Function dispatcher
FUNCTION_MAP = {
    "search_invoices": fn_search_invoices,
    "get_partner_totals": fn_get_partner_totals,
    "get_revenue_costs": fn_get_revenue_costs,
    "search_partners": fn_search_partners,
    "get_account_balance": fn_get_account_balance,
    "get_open_items": fn_get_open_items,
    "get_bank_balance": fn_get_bank_balance
}

def execute_function_call(function_name, arguments):
    """Voer een function call uit"""
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        if function_name in FUNCTION_MAP:
            return FUNCTION_MAP[function_name](**args), None
        else:
            return None, f"Onbekende functie: {function_name}"
    except Exception as e:
        return None, f"Functie fout: {e}"

def process_chat_message(user_message, chat_history, context_info):
    """Verwerk een chat bericht met function calling"""
    
    # Bouw berichten op voor OpenAI
    messages = [
        {"role": "system", "content": CHATBOT_SYSTEM_PROMPT + f"\n\nHuidige context:\n{context_info}"}
    ]
    
    # Voeg chat geschiedenis toe
    for msg in chat_history[-10:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    
    # Voeg nieuwe vraag toe
    messages.append({"role": "user", "content": user_message})
    
    # Eerste OpenAI call met functions
    response_msg, error = call_openai_with_functions(messages, ODOO_FUNCTIONS)
    if error:
        return f"❌ {error}", None
    
    all_results = []
    
    # Check voor tool calls
    tool_calls = response_msg.get("tool_calls", [])
    
    if tool_calls:
        messages.append(response_msg)
        
        for tool_call in tool_calls:
            fn_name = tool_call["function"]["name"]
            fn_args = tool_call["function"]["arguments"]
            
            result, fn_error = execute_function_call(fn_name, fn_args)
            
            if fn_error:
                tool_result = {"error": fn_error}
            else:
                tool_result = result
                all_results.append({"function": fn_name, "result": result})
            
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": json.dumps(tool_result, default=str)
            })
        
        # Tweede call voor het antwoord
        final_msg, error = call_openai_with_functions(messages, None)
        if error:
            return f"❌ {error}", all_results
        
        return final_msg.get("content", ""), all_results
    
    # Geen function calls - direct antwoord
    return response_msg.get("content", ""), None

# =============================================================================
# MONTHLY CLOSING CHECKLIST FUNCTIES
# =============================================================================

CLOSING_PASSWORD = "controller"

MONTH_NAMES_NL = {
    1: "Januari", 2: "Februari", 3: "Maart", 4: "April",
    5: "Mei", 6: "Juni", 7: "Juli", 8: "Augustus",
    9: "September", 10: "Oktober", 11: "November", 12: "December"
}

def get_unposted_invoices(year: int, month: int, company_id: Optional[int] = None) -> List[Dict]:
    """Haal ongeboekte facturen op voor een specifieke maand."""
    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"
    
    domain = [
        ["invoice_date", ">=", start_date],
        ["invoice_date", "<", end_date],
        ["state", "=", "draft"],
        ["move_type", "in", ["out_invoice", "out_refund", "in_invoice", "in_refund"]]
    ]
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    return odoo_call(
        "account.move", "search_read",
        domain,
        ["name", "partner_id", "invoice_date", "amount_total", "move_type", "company_id", "ref"],
        limit=500
    )

def get_unreconciled_bank_lines(year: int, month: int, company_id: Optional[int] = None) -> List[Dict]:
    """Haal niet-afgeletterde bankregels op voor een specifieke maand."""
    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"
    
    domain = [
        ["journal_id.type", "=", "bank"],
        ["is_reconciled", "=", False],
        ["parent_state", "=", "posted"],
        ["date", ">=", start_date],
        ["date", "<", end_date]
    ]
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    return odoo_call(
        "account.move.line", "search_read",
        domain,
        ["date", "name", "ref", "debit", "credit", "partner_id", "journal_id", "company_id"],
        limit=500
    )

def get_intercompany_balances(year: int, month: int) -> Dict[str, Dict]:
    """Haal intercompany saldi op per entiteit voor reconciliatie check."""
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"
    
    ic_balances = {}
    
    for comp_id, comp_name in COMPANIES.items():
        # Vorderingen op groepsmaatschappijen (12xxx)
        vorderingen = odoo_read_group(
            "account.move.line",
            [
                ("account_id.code", ">=", "120000"),
                ("account_id.code", "<", "130000"),
                ("date", "<", end_date),
                ("parent_state", "=", "posted"),
                ("company_id", "=", comp_id)
            ],
            ["balance:sum"],
            ["partner_id"]
        )
        
        # Schulden aan groepsmaatschappijen (14xxx)
        schulden = odoo_read_group(
            "account.move.line",
            [
                ("account_id.code", ">=", "140000"),
                ("account_id.code", "<", "150000"),
                ("date", "<", end_date),
                ("parent_state", "=", "posted"),
                ("company_id", "=", comp_id)
            ],
            ["balance:sum"],
            ["partner_id"]
        )
        
        ic_balances[comp_name] = {
            "vorderingen": vorderingen,
            "schulden": schulden,
            "netto_vordering": sum(v.get("balance", 0) for v in vorderingen),
            "netto_schuld": sum(s.get("balance", 0) for s in schulden)
        }
    
    return ic_balances

def get_unapproved_vendor_bills(year: int, month: int, company_id: Optional[int] = None) -> List[Dict]:
    """Haal niet-goedgekeurde leveranciersfacturen op (LAB specifiek veld)."""
    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"
    
    domain = [
        ["invoice_date", ">=", start_date],
        ["invoice_date", "<", end_date],
        ["move_type", "=", "in_invoice"],
        ["state", "=", "posted"],
        ["vendor_bill_approved", "=", False]
    ]
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    try:
        return odoo_call(
            "account.move", "search_read",
            domain,
            ["name", "partner_id", "invoice_date", "amount_total", "company_id", "ref"],
            limit=200
        )
    except:
        return []

def get_overdue_receivables(days: int = 30, company_id: Optional[int] = None) -> List[Dict]:
    """Haal vervallen debiteuren op."""
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    domain = [
        ["account_id.account_type", "=", "asset_receivable"],
        ["parent_state", "=", "posted"],
        ["amount_residual", "!=", 0],
        ["date_maturity", "<", cutoff_date]
    ]
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    return odoo_call(
        "account.move.line", "search_read",
        domain,
        ["partner_id", "date_maturity", "amount_residual", "move_id", "company_id"],
        limit=500,
        include_archived=True
    )

def get_overdue_payables(days: int = 30, company_id: Optional[int] = None) -> List[Dict]:
    """Haal vervallen crediteuren op."""
    cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    
    domain = [
        ["account_id.account_type", "=", "liability_payable"],
        ["parent_state", "=", "posted"],
        ["amount_residual", "!=", 0],
        ["date_maturity", "<", cutoff_date]
    ]
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    return odoo_call(
        "account.move.line", "search_read",
        domain,
        ["partner_id", "date_maturity", "amount_residual", "move_id", "company_id"],
        limit=500,
        include_archived=True
    )

def get_missing_partner_entries(year: int, month: int, company_id: Optional[int] = None) -> List[Dict]:
    """Haal boekingen zonder partner op debiteur/crediteur rekeningen."""
    start_date = f"{year}-{month:02d}-01"
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"
    
    domain = [
        ["date", ">=", start_date],
        ["date", "<", end_date],
        ["parent_state", "=", "posted"],
        ["partner_id", "=", False],
        "|",
        ["account_id.account_type", "=", "asset_receivable"],
        ["account_id.account_type", "=", "liability_payable"]
    ]
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    return odoo_call(
        "account.move.line", "search_read",
        domain,
        ["date", "name", "move_id", "account_id", "debit", "credit", "company_id"],
        limit=200
    )

def get_suspense_account_balance(year: int, month: int, company_id: Optional[int] = None) -> Tuple[float, List[Dict]]:
    """Haal saldo en details van tussenrekeningen (vraagposten)."""
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"
    
    # Tussenrekeningen (19xxx, 29xxx)
    domain = [
        "|",
        "&", ["account_id.code", ">=", "190000"], ["account_id.code", "<", "200000"],
        "&", ["account_id.code", ">=", "290000"], ["account_id.code", "<", "300000"],
        ["date", "<", end_date],
        ["parent_state", "=", "posted"],
        ["balance", "!=", 0]
    ]
    if company_id:
        domain.append(["company_id", "=", company_id])
    
    lines = odoo_call(
        "account.move.line", "search_read",
        domain,
        ["date", "name", "account_id", "balance", "partner_id", "company_id", "move_id"],
        limit=100
    )
    
    total = sum(l.get("balance", 0) for l in lines)
    return total, lines

def get_vat_to_declare(year: int, month: int, company_id: Optional[int] = None) -> Dict:
    """Haal BTW saldi op voor aangifte check."""
    if month == 12:
        end_date = f"{year + 1}-01-01"
    else:
        end_date = f"{year}-{month + 1:02d}-01"
    
    start_date = f"{year}-{month:02d}-01"
    
    # Af te dragen BTW (15xxx)
    btw_af = odoo_read_group(
        "account.move.line",
        [
            ("account_id.code", ">=", "150000"),
            ("account_id.code", "<", "160000"),
            ("date", ">=", start_date),
            ("date", "<", end_date),
            ("parent_state", "=", "posted"),
            ("company_id", "=", company_id) if company_id else ("id", "!=", 0)
        ],
        ["balance:sum"],
        []
    )
    
    # Te vorderen BTW (18xxx)
    btw_te_vorderen = odoo_read_group(
        "account.move.line",
        [
            ("account_id.code", ">=", "180000"),
            ("account_id.code", "<", "190000"),
            ("date", ">=", start_date),
            ("date", "<", end_date),
            ("parent_state", "=", "posted"),
            ("company_id", "=", company_id) if company_id else ("id", "!=", 0)
        ],
        ["balance:sum"],
        []
    )
    
    return {
        "btw_af": btw_af[0].get("balance", 0) if btw_af else 0,
        "btw_te_vorderen": btw_te_vorderen[0].get("balance", 0) if btw_te_vorderen else 0,
        "netto": (btw_af[0].get("balance", 0) if btw_af else 0) + (btw_te_vorderen[0].get("balance", 0) if btw_te_vorderen else 0)
    }

def get_pl_anomalies(year: int, month: int, company_id: Optional[int] = None, 
                     threshold_pct: float = 50.0, threshold_abs: float = 5000.0) -> Dict:
    """
    Analyseer W&V en detecteer anomalieën t.o.v.:
    1. Vorige maand
    2. Gemiddelde van afgelopen 12 maanden
    
    Returns dict met:
    - current_month: huidige maand per categorie
    - previous_month: vorige maand per categorie
    - avg_12m: 12-maands gemiddelde per categorie
    - anomalies: lijst van afwijkingen
    """
    from datetime import datetime
    from dateutil.relativedelta import relativedelta
    
    # Bereken datums
    current_start = datetime(year, month, 1)
    current_end = current_start + relativedelta(months=1)
    
    prev_start = current_start - relativedelta(months=1)
    prev_end = current_start
    
    # 12 maanden geleden t/m vorige maand
    avg_start = current_start - relativedelta(months=12)
    avg_end = current_start
    
    # W&V categorieën (4xxx=omzet, 7xxx=kosten, 8xxx=kosten, 9xxx=afschrijvingen)
    categories = [
        ("40", "Omzet handelsgoederen"),
        ("41", "Omzet diensten"),
        ("42", "Omzet projecten"),
        ("43", "Overige omzet"),
        ("70", "Inkoopkosten"),
        ("74", "Personeelskosten"),
        ("75", "Huisvestingskosten"),
        ("76", "Verkoopkosten"),
        ("77", "Autokosten"),
        ("78", "Kantoorkosten"),
        ("79", "Algemene kosten"),
        ("80", "Afschrijvingen"),
        ("84", "Financiële baten/lasten"),
        ("85", "Bijzondere baten/lasten"),
    ]
    
    results = {
        "current_month": {},
        "previous_month": {},
        "avg_12m": {},
        "anomalies": [],
        "period": f"{year}-{month:02d}"
    }
    
    company_filter = [("company_id", "=", company_id)] if company_id else []
    
    for code_prefix, name in categories:
        # Huidige maand
        current = odoo_read_group(
            "account.move.line",
            [
                ("account_id.code", ">=", f"{code_prefix}0000"),
                ("account_id.code", "<", f"{int(code_prefix) + 1}0000" if len(code_prefix) == 2 else f"{code_prefix[0]}{int(code_prefix[1]) + 1}0000"),
                ("date", ">=", current_start.strftime("%Y-%m-%d")),
                ("date", "<", current_end.strftime("%Y-%m-%d")),
                ("parent_state", "=", "posted"),
            ] + company_filter,
            ["balance:sum"],
            []
        )
        current_val = current[0].get("balance", 0) if current else 0
        
        # Vorige maand
        previous = odoo_read_group(
            "account.move.line",
            [
                ("account_id.code", ">=", f"{code_prefix}0000"),
                ("account_id.code", "<", f"{int(code_prefix) + 1}0000" if len(code_prefix) == 2 else f"{code_prefix[0]}{int(code_prefix[1]) + 1}0000"),
                ("date", ">=", prev_start.strftime("%Y-%m-%d")),
                ("date", "<", prev_end.strftime("%Y-%m-%d")),
                ("parent_state", "=", "posted"),
            ] + company_filter,
            ["balance:sum"],
            []
        )
        prev_val = previous[0].get("balance", 0) if previous else 0
        
        # 12-maanden totaal (voor gemiddelde)
        avg_12 = odoo_read_group(
            "account.move.line",
            [
                ("account_id.code", ">=", f"{code_prefix}0000"),
                ("account_id.code", "<", f"{int(code_prefix) + 1}0000" if len(code_prefix) == 2 else f"{code_prefix[0]}{int(code_prefix[1]) + 1}0000"),
                ("date", ">=", avg_start.strftime("%Y-%m-%d")),
                ("date", "<", avg_end.strftime("%Y-%m-%d")),
                ("parent_state", "=", "posted"),
            ] + company_filter,
            ["balance:sum"],
            []
        )
        avg_val = (avg_12[0].get("balance", 0) / 12) if avg_12 else 0
        
        # Opslaan
        results["current_month"][code_prefix] = {"name": name, "value": current_val}
        results["previous_month"][code_prefix] = {"name": name, "value": prev_val}
        results["avg_12m"][code_prefix] = {"name": name, "value": avg_val}
        
        # Check anomalieën vs vorige maand
        if prev_val != 0:
            pct_change_prev = ((current_val - prev_val) / abs(prev_val)) * 100
            abs_change_prev = current_val - prev_val
            
            if abs(pct_change_prev) >= threshold_pct and abs(abs_change_prev) >= threshold_abs:
                results["anomalies"].append({
                    "category": name,
                    "code": code_prefix,
                    "type": "vs_vorige_maand",
                    "current": current_val,
                    "comparison": prev_val,
                    "pct_change": pct_change_prev,
                    "abs_change": abs_change_prev,
                    "severity": "high" if abs(pct_change_prev) >= 100 else "medium"
                })
        elif current_val != 0 and abs(current_val) >= threshold_abs:
            # Vorige maand was 0, nu niet
            results["anomalies"].append({
                "category": name,
                "code": code_prefix,
                "type": "vs_vorige_maand",
                "current": current_val,
                "comparison": 0,
                "pct_change": float('inf'),
                "abs_change": current_val,
                "severity": "high"
            })
        
        # Check anomalieën vs 12-maands gemiddelde
        if avg_val != 0:
            pct_change_avg = ((current_val - avg_val) / abs(avg_val)) * 100
            abs_change_avg = current_val - avg_val
            
            if abs(pct_change_avg) >= threshold_pct and abs(abs_change_avg) >= threshold_abs:
                # Voorkom dubbele meldingen als al vs vorige maand gemeld
                already_reported = any(
                    a["code"] == code_prefix and a["type"] == "vs_vorige_maand" 
                    for a in results["anomalies"]
                )
                results["anomalies"].append({
                    "category": name,
                    "code": code_prefix,
                    "type": "vs_12m_gemiddelde",
                    "current": current_val,
                    "comparison": avg_val,
                    "pct_change": pct_change_avg,
                    "abs_change": abs_change_avg,
                    "severity": "high" if abs(pct_change_avg) >= 100 else "medium",
                    "also_vs_prev": already_reported
                })
    
    # Sorteer anomalieën op severity en absolute change
    results["anomalies"].sort(key=lambda x: (0 if x["severity"] == "high" else 1, -abs(x["abs_change"])))
    
    return results

def get_pl_details_for_category(year: int, month: int, code_prefix: str, company_id: Optional[int] = None) -> List[Dict]:
    """Haal gedetailleerde W&V boekingen op voor een specifieke categorie."""
    from datetime import datetime
    from dateutil.relativedelta import relativedelta
    
    current_start = datetime(year, month, 1)
    current_end = current_start + relativedelta(months=1)
    
    company_filter = [("company_id", "=", company_id)] if company_id else []
    
    # Haal boekingen op per rekening
    details = odoo_read_group(
        "account.move.line",
        [
            ("account_id.code", ">=", f"{code_prefix}0000"),
            ("account_id.code", "<", f"{int(code_prefix) + 1}0000" if len(code_prefix) == 2 else f"{code_prefix[0]}{int(code_prefix[1]) + 1}0000"),
            ("date", ">=", current_start.strftime("%Y-%m-%d")),
            ("date", "<", current_end.strftime("%Y-%m-%d")),
            ("parent_state", "=", "posted"),
        ] + company_filter,
        ["account_id", "balance:sum"],
        ["account_id"]
    )
    
    result = []
    for d in details:
        if d.get("balance", 0) != 0:
            acc_name = d.get("account_id", [0, "Onbekend"])
            result.append({
                "account": acc_name[1] if isinstance(acc_name, list) else str(acc_name),
                "balance": d.get("balance", 0)
            })
    
    result.sort(key=lambda x: -abs(x["balance"]))
    return result

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
    st.caption("Real-time data uit Odoo | v13 - Met AI Chat & Maandafsluiting Checklist")
    
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
    # TAB 7: CASHFLOW
    # =========================================================================
    with tabs[6]:
        st.header("📈 Cashflow Prognose")
        
        entity_label = "alle entiteiten" if selected_entity == "Alle bedrijven" else COMPANIES.get(company_id, "")
        st.info(f"💡 Cashflow prognose voor **{entity_label}** gebaseerd op huidige saldi en gemiddelden.")
        
        # Huidige posities - gefilterd op geselecteerde entiteit
        bank_data = get_bank_balances()
        receivables, payables = get_receivables_payables(company_id)
        
        # Filter banksaldo op geselecteerde entiteit
        if selected_entity == "Alle bedrijven":
            current_bank = sum(b.get("current_statement_balance", 0) for b in bank_data)
        else:
            current_bank = sum(b.get("current_statement_balance", 0) for b in bank_data 
                             if b.get("company_id", [None])[0] == company_id)
        current_rec = sum(r.get("amount_residual", 0) for r in receivables)
        current_pay = abs(sum(p.get("amount_residual", 0) for p in payables))
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("🏦 Huidig Banksaldo", f"€{current_bank:,.0f}")
        with col2:
            st.metric("📥 Te Ontvangen", f"€{current_rec:,.0f}")
        with col3:
            st.metric("📤 Te Betalen", f"€{current_pay:,.0f}")
        
        st.markdown("---")
        
        # Aannames
        st.subheader("⚙️ Aannames (pas aan)")
        col1, col2 = st.columns(2)
        with col1:
            weekly_revenue = st.number_input("Verwachte wekelijkse omzet", value=50000, step=5000)
            collection_rate = st.slider("Incasso % debiteuren per week", 0, 100, 25)
        with col2:
            weekly_costs = st.number_input("Verwachte wekelijkse kosten", value=45000, step=5000)
            payment_rate = st.slider("Betaling % crediteuren per week", 0, 100, 20)
        
        # Prognose berekenen
        weeks = 12
        forecast = []
        balance = current_bank
        remaining_rec = current_rec
        remaining_pay = current_pay
        
        for week in range(1, weeks + 1):
            # Ontvangsten
            collections = remaining_rec * (collection_rate / 100)
            remaining_rec -= collections
            inflow = weekly_revenue + collections
            
            # Betalingen
            payments = remaining_pay * (payment_rate / 100)
            remaining_pay -= payments
            outflow = weekly_costs + payments
            
            # Nieuw saldo
            balance = balance + inflow - outflow
            
            forecast.append({
                "Week": f"Week {week}",
                "Ontvangsten": inflow,
                "Betalingen": outflow,
                "Banksaldo": balance
            })
        
        df_forecast = pd.DataFrame(forecast)
        
        # Grafiek
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_forecast["Week"], y=df_forecast["Banksaldo"],
            mode="lines+markers", name="Banksaldo",
            line=dict(color="#1e3a5f", width=3)
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="red")
        fig.update_layout(height=400, title="📈 12-Weken Cashflow Prognose")
        st.plotly_chart(fig, use_container_width=True)
        
        # Tabel
        st.dataframe(
            df_forecast.style.format({
                "Ontvangsten": "€{:,.0f}",
                "Betalingen": "€{:,.0f}",
                "Banksaldo": "€{:,.0f}"
            }),
            use_container_width=True, hide_index=True
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
                        if message.get("functions_called"):
                            with st.expander(f"🔧 Functies aangeroepen ({len(message['functions_called'])})"):
                                for fn_call in message["functions_called"]:
                                    st.markdown(f"**`{fn_call['function']}`**")
                                    if fn_call.get("result"):
                                        st.json(fn_call["result"])
            
            # Chat input
            if prompt := st.chat_input("Stel een vraag over je financiële data..."):
                # Toon user message
                with st.chat_message("user"):
                    st.markdown(prompt)
                st.session_state.chat_messages.append({"role": "user", "content": prompt})
                
                # Genereer antwoord
                with st.chat_message("assistant"):
                    with st.spinner("🔍 Data ophalen..."):
                        response, function_results = process_chat_message(
                            prompt, 
                            st.session_state.chat_messages, 
                            context_info
                        )
                        st.markdown(response)
                        
                        if function_results:
                            with st.expander(f"🔧 Functies aangeroepen ({len(function_results)})"):
                                for fn_call in function_results:
                                    st.markdown(f"**`{fn_call['function']}`**")
                                    if fn_call.get("result"):
                                        st.json(fn_call["result"])
                
                # Sla antwoord op
                st.session_state.chat_messages.append({
                    "role": "assistant", 
                    "content": response,
                    "functions_called": function_results
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
    # TAB 10: MAANDAFSLUITING CHECKLIST
    # =========================================================================
    with tabs[9]:
        st.header("📋 Maandafsluiting Checklist")
        
        # Password protection
        if "closing_authenticated" not in st.session_state:
            st.session_state.closing_authenticated = False
        
        if not st.session_state.closing_authenticated:
            st.warning("🔐 Deze pagina is beveiligd. Voer het wachtwoord in om toegang te krijgen.")
            
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                password_input = st.text_input("Wachtwoord", type="password", key="closing_password")
                if st.button("🔓 Inloggen", use_container_width=True):
                    if password_input == CLOSING_PASSWORD:
                        st.session_state.closing_authenticated = True
                        st.rerun()
                    else:
                        st.error("❌ Onjuist wachtwoord")
        else:
            # Logout knop
            col_logout = st.columns([4, 1])[1]
            with col_logout:
                if st.button("🚪 Uitloggen"):
                    st.session_state.closing_authenticated = False
                    st.rerun()
            
            # Maand/Jaar selectie voor closing
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                closing_year = st.selectbox("📅 Jaar", years, index=0, key="closing_year")
            with col2:
                # Vorige maand als default
                current_month = datetime.now().month
                default_month_idx = current_month - 2 if current_month > 1 else 11
                closing_month = st.selectbox(
                    "📆 Maand", 
                    list(MONTH_NAMES_NL.items()),
                    index=default_month_idx,
                    format_func=lambda x: x[1],
                    key="closing_month"
                )[0]
            
            closing_month_name = MONTH_NAMES_NL[closing_month]
            st.subheader(f"🗓️ Afsluiting {closing_month_name} {closing_year}")
            
            # Initialize checklist state
            if "closing_checklist" not in st.session_state:
                st.session_state.closing_checklist = {}
            checklist_key = f"{closing_year}_{closing_month}"
            if checklist_key not in st.session_state.closing_checklist:
                st.session_state.closing_checklist[checklist_key] = {
                    "verkoop_facturen_geboekt": False,
                    "inkoop_facturen_geboekt": False,
                    "inkoop_goedgekeurd": False,
                    "bank_afgeleterd": False,
                    "intercompany_gecontroleerd": False,
                    "btw_gecontroleerd": False,
                    "vraagposten_opgelost": False,
                    "debiteuren_geanalyseerd": False,
                    "crediteuren_geanalyseerd": False,
                    "wv_anomalieen_geanalyseerd": False,
                    "periodeafsluiting_odoo": False,
                    "rapportage_verstuurd": False
                }
            
            checklist = st.session_state.closing_checklist[checklist_key]
            
            # Load data with spinner
            with st.spinner(f"Data laden voor {closing_month_name} {closing_year}..."):
                unposted = get_unposted_invoices(closing_year, closing_month, company_id)
                unposted_sales = [i for i in unposted if i.get("move_type", "").startswith("out")]
                unposted_purchase = [i for i in unposted if i.get("move_type", "").startswith("in")]
                
                unreconciled = get_unreconciled_bank_lines(closing_year, closing_month, company_id)
                unapproved = get_unapproved_vendor_bills(closing_year, closing_month, company_id)
                ic_balances = get_intercompany_balances(closing_year, closing_month)
                suspense_total, suspense_lines = get_suspense_account_balance(closing_year, closing_month, company_id)
                vat_data = get_vat_to_declare(closing_year, closing_month, company_id)
                overdue_rec = get_overdue_receivables(30, company_id)
                overdue_pay = get_overdue_payables(30, company_id)
            
            # Calculate overall progress
            total_items = len(checklist)
            completed_items = sum(1 for v in checklist.values() if v)
            progress = completed_items / total_items
            
            # Progress bar
            st.progress(progress, text=f"Voortgang: {completed_items}/{total_items} ({progress*100:.0f}%)")
            
            # ===== SECTIE 1: FACTUREN =====
            st.markdown("---")
            st.markdown("### 📄 Facturen")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Verkoopfacturen
                sales_status = "✅" if len(unposted_sales) == 0 else f"⚠️ {len(unposted_sales)}"
                checklist["verkoop_facturen_geboekt"] = st.checkbox(
                    f"Verkoopfacturen geboekt {sales_status}",
                    value=checklist["verkoop_facturen_geboekt"],
                    key=f"cb_sales_{checklist_key}"
                )
                if unposted_sales:
                    with st.expander(f"🔍 {len(unposted_sales)} ongeboekte verkoopfacturen"):
                        for inv in unposted_sales[:10]:
                            partner = inv.get("partner_id", ["", "Onbekend"])[1] if inv.get("partner_id") else "Geen"
                            st.write(f"• {inv.get('name', 'Draft')} - {partner} - €{inv.get('amount_total', 0):,.2f}")
                        if len(unposted_sales) > 10:
                            st.caption(f"...en {len(unposted_sales) - 10} meer")
            
            with col2:
                # Inkoopfacturen
                purchase_status = "✅" if len(unposted_purchase) == 0 else f"⚠️ {len(unposted_purchase)}"
                checklist["inkoop_facturen_geboekt"] = st.checkbox(
                    f"Inkoopfacturen geboekt {purchase_status}",
                    value=checklist["inkoop_facturen_geboekt"],
                    key=f"cb_purchase_{checklist_key}"
                )
                if unposted_purchase:
                    with st.expander(f"🔍 {len(unposted_purchase)} ongeboekte inkoopfacturen"):
                        for inv in unposted_purchase[:10]:
                            partner = inv.get("partner_id", ["", "Onbekend"])[1] if inv.get("partner_id") else "Geen"
                            st.write(f"• {inv.get('name', 'Draft')} - {partner} - €{inv.get('amount_total', 0):,.2f}")
                        if len(unposted_purchase) > 10:
                            st.caption(f"...en {len(unposted_purchase) - 10} meer")
            
            # Goedkeuring inkoopfacturen (LAB specifiek)
            approval_status = "✅" if len(unapproved) == 0 else f"⚠️ {len(unapproved)}"
            checklist["inkoop_goedgekeurd"] = st.checkbox(
                f"Inkoopfacturen goedgekeurd {approval_status}",
                value=checklist["inkoop_goedgekeurd"],
                key=f"cb_approval_{checklist_key}"
            )
            if unapproved:
                with st.expander(f"🔍 {len(unapproved)} niet-goedgekeurde inkoopfacturen"):
                    for inv in unapproved[:10]:
                        partner = inv.get("partner_id", ["", "Onbekend"])[1] if inv.get("partner_id") else "Geen"
                        company = COMPANIES.get(inv.get("company_id", [0])[0], "?")
                        st.write(f"• {inv.get('name')} - {partner} - €{inv.get('amount_total', 0):,.2f} ({company})")
            
            # ===== SECTIE 2: BANK =====
            st.markdown("---")
            st.markdown("### 🏦 Bank & Reconciliatie")
            
            bank_status = "✅" if len(unreconciled) == 0 else f"⚠️ {len(unreconciled)}"
            checklist["bank_afgeleterd"] = st.checkbox(
                f"Bankregels afgeleterd {bank_status}",
                value=checklist["bank_afgeleterd"],
                key=f"cb_bank_{checklist_key}"
            )
            if unreconciled:
                with st.expander(f"🔍 {len(unreconciled)} niet-afgeletterde bankregels"):
                    # Groepeer per journal
                    by_journal = {}
                    for line in unreconciled:
                        journal = line.get("journal_id", [0, "Onbekend"])[1] if line.get("journal_id") else "Onbekend"
                        if journal not in by_journal:
                            by_journal[journal] = []
                        by_journal[journal].append(line)
                    
                    for journal, lines in by_journal.items():
                        st.markdown(f"**{journal}** ({len(lines)} regels)")
                        for line in lines[:5]:
                            amount = line.get("debit", 0) - line.get("credit", 0)
                            st.write(f"  • {line.get('date')} - {line.get('name', '')[:40]} - €{amount:,.2f}")
                        if len(lines) > 5:
                            st.caption(f"  ...en {len(lines) - 5} meer")
            
            # ===== SECTIE 3: INTERCOMPANY =====
            st.markdown("---")
            st.markdown("### 🔄 Intercompany Reconciliatie")
            
            # Check IC balansen
            ic_issues = []
            total_vorderingen = sum(ic["netto_vordering"] for ic in ic_balances.values())
            total_schulden = sum(ic["netto_schuld"] for ic in ic_balances.values())
            ic_netto = total_vorderingen + total_schulden
            
            if abs(ic_netto) > 1:  # Meer dan €1 verschil
                ic_issues.append(f"Netto verschil: €{ic_netto:,.2f}")
            
            ic_status = "✅" if len(ic_issues) == 0 else f"⚠️ €{abs(ic_netto):,.0f} verschil"
            checklist["intercompany_gecontroleerd"] = st.checkbox(
                f"Intercompany saldi gecontroleerd {ic_status}",
                value=checklist["intercompany_gecontroleerd"],
                key=f"cb_ic_{checklist_key}"
            )
            
            with st.expander("🔍 Intercompany posities per entiteit"):
                ic_df_data = []
                for comp_name, data in ic_balances.items():
                    ic_df_data.append({
                        "Entiteit": comp_name,
                        "Vorderingen (12xxx)": data["netto_vordering"],
                        "Schulden (14xxx)": data["netto_schuld"],
                        "Netto": data["netto_vordering"] + data["netto_schuld"]
                    })
                
                df_ic = pd.DataFrame(ic_df_data)
                st.dataframe(
                    df_ic.style.format({
                        "Vorderingen (12xxx)": "€{:,.0f}",
                        "Schulden (14xxx)": "€{:,.0f}",
                        "Netto": "€{:,.0f}"
                    }),
                    use_container_width=True,
                    hide_index=True
                )
                
                # Totaal
                st.markdown(f"**Totaal vorderingen:** €{total_vorderingen:,.0f}")
                st.markdown(f"**Totaal schulden:** €{total_schulden:,.0f}")
                
                if abs(ic_netto) > 1:
                    st.warning(f"⚠️ **Netto verschil: €{ic_netto:,.2f}** - Dit moet €0 zijn!")
                else:
                    st.success("✅ Intercompany saldi zijn in balans")
            
            # ===== SECTIE 4: BTW =====
            st.markdown("---")
            st.markdown("### 🧾 BTW")
            
            vat_status = "ℹ️" if vat_data["netto"] != 0 else "✅"
            checklist["btw_gecontroleerd"] = st.checkbox(
                f"BTW gecontroleerd - Netto: €{abs(vat_data['netto']):,.0f}",
                value=checklist["btw_gecontroleerd"],
                key=f"cb_vat_{checklist_key}"
            )
            
            with st.expander("🔍 BTW Details"):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Af te dragen (15xxx)", f"€{abs(vat_data['btw_af']):,.0f}")
                with col2:
                    st.metric("Te vorderen (18xxx)", f"€{vat_data['btw_te_vorderen']:,.0f}")
                with col3:
                    if vat_data["netto"] < 0:
                        st.metric("Te betalen", f"€{abs(vat_data['netto']):,.0f}", delta="Schuld")
                    else:
                        st.metric("Te ontvangen", f"€{vat_data['netto']:,.0f}", delta="Vordering")
            
            # ===== SECTIE 5: VRAAGPOSTEN =====
            st.markdown("---")
            st.markdown("### ❓ Vraagposten & Tussenrekeningen")
            
            suspense_status = "✅" if abs(suspense_total) < 1 else f"⚠️ €{abs(suspense_total):,.0f}"
            checklist["vraagposten_opgelost"] = st.checkbox(
                f"Vraagposten opgelost {suspense_status}",
                value=checklist["vraagposten_opgelost"],
                key=f"cb_suspense_{checklist_key}"
            )
            
            if suspense_lines:
                with st.expander(f"🔍 {len(suspense_lines)} openstaande vraagposten"):
                    for line in suspense_lines[:15]:
                        account = line.get("account_id", [0, "?"])[1] if line.get("account_id") else "?"
                        st.write(f"• {line.get('date')} - {account} - {line.get('name', '')[:40]} - €{line.get('balance', 0):,.2f}")
            
            # ===== SECTIE 6: DEBITEUREN & CREDITEUREN =====
            st.markdown("---")
            st.markdown("### 👥 Debiteuren & Crediteuren Analyse")
            
            col1, col2 = st.columns(2)
            
            with col1:
                overdue_rec_total = sum(r.get("amount_residual", 0) for r in overdue_rec)
                rec_status = "✅" if len(overdue_rec) == 0 else f"⚠️ {len(overdue_rec)} ({f'€{overdue_rec_total:,.0f}'})"
                checklist["debiteuren_geanalyseerd"] = st.checkbox(
                    f"Vervallen debiteuren >30d {rec_status}",
                    value=checklist["debiteuren_geanalyseerd"],
                    key=f"cb_rec_{checklist_key}"
                )
                if overdue_rec:
                    with st.expander(f"🔍 Top 10 vervallen debiteuren"):
                        # Groepeer per partner
                        by_partner = {}
                        for line in overdue_rec:
                            partner = line.get("partner_id", [0, "Onbekend"])[1] if line.get("partner_id") else "Onbekend"
                            if partner not in by_partner:
                                by_partner[partner] = 0
                            by_partner[partner] += line.get("amount_residual", 0)
                        
                        sorted_partners = sorted(by_partner.items(), key=lambda x: -x[1])[:10]
                        for partner, amount in sorted_partners:
                            st.write(f"• {partner}: €{amount:,.2f}")
            
            with col2:
                overdue_pay_total = sum(p.get("amount_residual", 0) for p in overdue_pay)
                pay_status = "✅" if len(overdue_pay) == 0 else f"⚠️ {len(overdue_pay)} ({f'€{abs(overdue_pay_total):,.0f}'})"
                checklist["crediteuren_geanalyseerd"] = st.checkbox(
                    f"Vervallen crediteuren >30d {pay_status}",
                    value=checklist["crediteuren_geanalyseerd"],
                    key=f"cb_pay_{checklist_key}"
                )
                if overdue_pay:
                    with st.expander(f"🔍 Top 10 vervallen crediteuren"):
                        by_partner = {}
                        for line in overdue_pay:
                            partner = line.get("partner_id", [0, "Onbekend"])[1] if line.get("partner_id") else "Onbekend"
                            if partner not in by_partner:
                                by_partner[partner] = 0
                            by_partner[partner] += abs(line.get("amount_residual", 0))
                        
                        sorted_partners = sorted(by_partner.items(), key=lambda x: -x[1])[:10]
                        for partner, amount in sorted_partners:
                            st.write(f"• {partner}: €{amount:,.2f}")
            
            # ===== SECTIE 7: W&V ANOMALIEËN =====
            st.markdown("---")
            st.markdown("### 📊 Winst & Verlies Anomalieën")
            st.caption("Detecteert ongebruikelijke afwijkingen t.o.v. vorige maand en 12-maands gemiddelde")
            
            # Drempel instellingen
            with st.expander("⚙️ Anomalie drempels aanpassen"):
                thresh_col1, thresh_col2 = st.columns(2)
                with thresh_col1:
                    threshold_pct = st.slider(
                        "Minimale afwijking (%)",
                        min_value=10,
                        max_value=200,
                        value=50,
                        step=10,
                        help="Afwijking moet minstens dit percentage zijn"
                    )
                with thresh_col2:
                    threshold_abs = st.slider(
                        "Minimale afwijking (€)",
                        min_value=1000,
                        max_value=50000,
                        value=5000,
                        step=1000,
                        help="Afwijking moet minstens dit bedrag zijn"
                    )
                st.info(f"Huidige drempels: >{threshold_pct}% afwijking EN >€{threshold_abs:,} verschil")
            
            # Haal P&L anomalie data op
            with st.spinner("W&V analyse laden..."):
                pl_data = get_pl_anomalies(closing_year, closing_month, company_id, threshold_pct, threshold_abs)
            
            anomalies = pl_data.get("anomalies", [])
            high_severity = [a for a in anomalies if a.get("severity") == "high"]
            medium_severity = [a for a in anomalies if a.get("severity") == "medium"]
            
            pl_status = "✅" if len(anomalies) == 0 else f"⚠️ {len(anomalies)} afwijkingen"
            checklist["wv_anomalieen_geanalyseerd"] = st.checkbox(
                f"W&V anomalieën geanalyseerd {pl_status}",
                value=checklist.get("wv_anomalieen_geanalyseerd", False),
                key=f"cb_pl_anom_{checklist_key}"
            )
            
            if anomalies:
                # Metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("🔴 Hoge afwijkingen", len(high_severity))
                with col2:
                    st.metric("🟡 Medium afwijkingen", len(medium_severity))
                with col3:
                    biggest = max(anomalies, key=lambda x: abs(x.get("abs_change", 0)))
                    st.metric("Grootste afwijking", f"€{abs(biggest.get('abs_change', 0)):,.0f}")
                
                # Detail tabel
                with st.expander(f"🔍 Alle {len(anomalies)} afwijkingen", expanded=True):
                    for anom in anomalies:
                        severity_icon = "🔴" if anom["severity"] == "high" else "🟡"
                        comparison_type = "vorige maand" if anom["type"] == "vs_vorige_maand" else "12-mnd gem."
                        
                        # Richting indicator
                        if anom["abs_change"] > 0:
                            direction = "📈" if anom["code"].startswith("4") else "📈⚠️"  # Omzet stijging = goed, kosten stijging = let op
                        else:
                            direction = "📉⚠️" if anom["code"].startswith("4") else "📉"  # Omzet daling = let op, kosten daling = goed
                        
                        pct_display = f"{anom['pct_change']:+.0f}%" if anom['pct_change'] != float('inf') else "NIEUW"
                        
                        st.markdown(f"""
                        {severity_icon} **{anom['category']}** ({anom['code']}xxx) {direction}
                        - Huidige maand: **€{anom['current']:,.0f}**
                        - {comparison_type.capitalize()}: €{anom['comparison']:,.0f}
                        - Verschil: **{pct_display}** (€{anom['abs_change']:+,.0f})
                        """)
                        
                        # Drill-down optie
                        if st.button(f"📋 Details {anom['code']}", key=f"pl_detail_{anom['code']}_{anom['type']}_{checklist_key}"):
                            details = get_pl_details_for_category(closing_year, closing_month, anom['code'], company_id)
                            if details:
                                st.write("**Boekingen per rekening:**")
                                for d in details[:10]:
                                    st.write(f"  • {d['account']}: €{d['balance']:,.2f}")
                        
                        st.markdown("---")
                
                # Vergelijkingstabel
                with st.expander("📊 Complete W&V vergelijking"):
                    comparison_data = []
                    for code in pl_data["current_month"]:
                        curr = pl_data["current_month"][code]
                        prev = pl_data["previous_month"].get(code, {"value": 0})
                        avg = pl_data["avg_12m"].get(code, {"value": 0})
                        
                        # Bereken afwijkingen
                        vs_prev = ((curr["value"] - prev["value"]) / abs(prev["value"]) * 100) if prev["value"] != 0 else 0
                        vs_avg = ((curr["value"] - avg["value"]) / abs(avg["value"]) * 100) if avg["value"] != 0 else 0
                        
                        comparison_data.append({
                            "Categorie": curr["name"],
                            "Code": f"{code}xxx",
                            f"Huidige ({closing_month:02d}/{closing_year})": curr["value"],
                            "Vorige maand": prev["value"],
                            "12-mnd gem.": avg["value"],
                            "% vs vorig": vs_prev,
                            "% vs gem.": vs_avg
                        })
                    
                    import pandas as pd
                    df_pl = pd.DataFrame(comparison_data)
                    
                    # Formattering
                    st.dataframe(
                        df_pl.style.format({
                            f"Huidige ({closing_month:02d}/{closing_year})": "€{:,.0f}",
                            "Vorige maand": "€{:,.0f}",
                            "12-mnd gem.": "€{:,.0f}",
                            "% vs vorig": "{:+.1f}%",
                            "% vs gem.": "{:+.1f}%"
                        }).applymap(
                            lambda x: "background-color: #ffcccb" if isinstance(x, (int, float)) and abs(x) > 50 else "",
                            subset=["% vs vorig", "% vs gem."]
                        ),
                        use_container_width=True
                    )
            else:
                st.success("✅ Geen significante W&V afwijkingen gedetecteerd!")
                st.caption(f"Drempels: >{threshold_pct}% afwijking EN >€{threshold_abs:,} verschil")
            
            # ===== SECTIE 8: AFSLUITING =====
            st.markdown("---")
            st.markdown("### ✅ Afsluiting")
            
            checklist["periodeafsluiting_odoo"] = st.checkbox(
                "Periode afgesloten in Odoo",
                value=checklist["periodeafsluiting_odoo"],
                key=f"cb_period_{checklist_key}",
                help="Sluit de periode in Odoo om te voorkomen dat er nog boekingen gemaakt worden"
            )
            
            checklist["rapportage_verstuurd"] = st.checkbox(
                "Maandrapportage verstuurd naar management",
                value=checklist["rapportage_verstuurd"],
                key=f"cb_report_{checklist_key}"
            )
            
            # Save checklist state
            st.session_state.closing_checklist[checklist_key] = checklist
            
            # ===== SAMENVATTING =====
            st.markdown("---")
            st.markdown("### 📊 Samenvatting")
            
            # Issues overzicht
            issues = []
            if len(unposted_sales) > 0:
                issues.append(f"📄 {len(unposted_sales)} ongeboekte verkoopfacturen")
            if len(unposted_purchase) > 0:
                issues.append(f"📄 {len(unposted_purchase)} ongeboekte inkoopfacturen")
            if len(unapproved) > 0:
                issues.append(f"❌ {len(unapproved)} niet-goedgekeurde facturen")
            if len(unreconciled) > 0:
                issues.append(f"🏦 {len(unreconciled)} niet-afgeletterde bankregels")
            if abs(ic_netto) > 1:
                issues.append(f"🔄 IC verschil: €{ic_netto:,.2f}")
            if abs(suspense_total) > 1:
                issues.append(f"❓ Vraagposten: €{suspense_total:,.2f}")
            if len(overdue_rec) > 0:
                issues.append(f"👥 {len(overdue_rec)} vervallen debiteuren (€{overdue_rec_total:,.0f})")
            if len(overdue_pay) > 0:
                issues.append(f"🏭 {len(overdue_pay)} vervallen crediteuren (€{abs(overdue_pay_total):,.0f})")
            if len(anomalies) > 0:
                high_count = len([a for a in anomalies if a.get("severity") == "high"])
                if high_count > 0:
                    issues.append(f"📊 {len(anomalies)} W&V anomalieën ({high_count} hoog)")
                else:
                    issues.append(f"📊 {len(anomalies)} W&V anomalieën")
            
            if issues:
                st.warning("**Openstaande punten:**")
                for issue in issues:
                    st.write(f"  • {issue}")
            else:
                st.success("🎉 Alle automatische checks zijn in orde!")
            
            # Checklist status
            unchecked = [k for k, v in checklist.items() if not v]
            if unchecked:
                st.info(f"**Nog af te vinken:** {len(unchecked)} items")
            else:
                st.balloons()
                st.success(f"🏆 Maandafsluiting {closing_month_name} {closing_year} is compleet!")
            
            # Export knop
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                # W&V anomalie samenvatting voor export
                num_anomalies = len(anomalies) if 'anomalies' in dir() else 0
                anomaly_text = ""
                if num_anomalies > 0:
                    anomaly_text = "\n\nW&V ANOMALIEËN:\n"
                    for anom in anomalies[:10]:
                        pct = f"{anom['pct_change']:+.0f}%" if anom['pct_change'] != float('inf') else "NIEUW"
                        anomaly_text += f"- {anom['category']}: €{anom['current']:,.0f} ({pct} vs {'vorige maand' if anom['type'] == 'vs_vorige_maand' else '12-mnd gem.'})\n"
                
                # Generate summary text
                summary_text = f"""MAANDAFSLUITING CHECKLIST - {closing_month_name} {closing_year}
{'='*50}

VOORTGANG: {completed_items}/{total_items} ({progress*100:.0f}%)

AUTOMATISCHE CHECKS:
- Ongeboekte verkoopfacturen: {len(unposted_sales)}
- Ongeboekte inkoopfacturen: {len(unposted_purchase)}
- Niet-goedgekeurde facturen: {len(unapproved)}
- Niet-afgeletterde bankregels: {len(unreconciled)}
- Intercompany verschil: €{ic_netto:,.2f}
- Vraagposten saldo: €{suspense_total:,.2f}
- Vervallen debiteuren: {len(overdue_rec)} (€{overdue_rec_total:,.0f})
- Vervallen crediteuren: {len(overdue_pay)} (€{abs(overdue_pay_total):,.0f})
- BTW netto: €{vat_data['netto']:,.2f}
- W&V anomalieën: {num_anomalies}
{anomaly_text}
CHECKLIST STATUS:
""" + "\n".join([f"- {'✅' if v else '❌'} {k.replace('_', ' ').title()}" for k, v in checklist.items()])
                
                st.download_button(
                    "📥 Download Checklist (TXT)",
                    summary_text,
                    file_name=f"maandafsluiting_{closing_year}_{closing_month:02d}.txt",
                    mime="text/plain"
                )
            
            with col2:
                if st.button("🔄 Ververs Data"):
                    st.cache_data.clear()
                    st.rerun()

if __name__ == "__main__":
    main()
