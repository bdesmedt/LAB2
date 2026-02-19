# LAB · Dashboard

Financieel dashboard voor LAB Group — gebouwd door [FID Finance](https://fidfinance.nl).

## 📱 Over

Een Progressive Web App (PWA) die real-time financieel inzicht biedt aan het management van LAB Group, zonder in Odoo te hoeven inloggen.

### Features
- **6 dashboardpagina's**: Home, Omzet & Marge, Kassaverkopen, Cash & Liquiditeit, Openstaande Posten, KPI Scorecard
- **Responsive**: Desktop sidebar + mobiele bottom navigation
- **PWA**: Installeerbaar op homescreen, offline support
- **Real-time data**: Automatische sync met Odoo (elke 15-60 min)
- **LAB branding**: Huisstijl met Playfair Display, Hunter Green, warm kleurenpalet

### Entiteiten
- LAB Shops (retail)
- LAB Conceptstore (POS/kassa)
- LAB Projects (projecten)
- Juloni (holding)
- MT Paints (productie)
- LAB Colour the World (internationaal)

## 🚀 Deployment

### Statisch hosten
De app is een single-file HTML applicatie. Geen build stap nodig.

```bash
# Lokaal testen
npx serve .

# Of simpelweg index.html openen in een browser
```

### Productie
Deploy op Vercel, Netlify, of elke statische hosting:
1. Push deze repo
2. Set build command: (none)
3. Set output directory: `.`
4. Configureer custom domein

## 📊 Data

De app laadt data uit `data/dashboard.json`. Dit bestand wordt automatisch bijgewerkt door de FID Finance sync engine die data ophaalt uit de 4 Odoo-systemen van LAB Group.

### Data architectuur
```
Odoo (4 systemen) → Sync Engine → dashboard.json → Browser
```

## 🔐 Beveiliging

- Alle data geaggregeerd (geen individuele transacties)
- HTTPS verplicht
- Authenticatie via JWT tokens (productie)
- Audit trail op alle toegang

## 📋 Licentie

Eigendom van FID Finance B.V. — ontwikkeld voor LAB Group.

---

*Powered by [FID Finance](https://fidfinance.nl)*
