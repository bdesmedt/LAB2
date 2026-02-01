# Financial Dashboard

Real-time financial analytics dashboard for LAB Groep, built with Streamlit and connected to Odoo ERP.

## Features

- **Financial Overview**: YTD revenue, costs, profit/loss with KPIs
- **Bank Balances**: Multi-entity bank account overview
- **Invoices**: Drill-down invoice management with PDF access
- **Products**: Product category analysis and top performers
- **Customer Map**: Geographic visualization of customers
- **Cost Analysis**: Cost breakdown by category
- **Cashflow Forecast**: 12-week cashflow projection
- **Balance Sheet**: Quadrant format balance sheet view
- **AI Chat**: Natural language financial queries (GPT-4)
- **Financial Close**: Password-protected monthly close workflow

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

### Required: Odoo API Key

The dashboard requires an Odoo API key to connect to the ERP system.

**Option 1: Streamlit Secrets (Recommended)**

Create a file `.streamlit/secrets.toml`:

```toml
ODOO_API_KEY = "your_odoo_api_key"
```

**Option 2: Manual Input**

Enter the API key in the sidebar when the dashboard loads.

### Optional: OpenAI API Key (for AI Chat)

To enable the AI Chat feature, add your OpenAI API key:

```toml
OPENAI_API_KEY = "your_openai_api_key"
```

Or enter it in the sidebar.

### Optional: Financial Close Password

The Financial Close (Maandafsluiting) tab provides sensitive financial closing workflows and requires password protection.

**Setting up the password:**

**Option 1: Streamlit Secrets (Recommended for Production)**

Add to your `.streamlit/secrets.toml` file:

```toml
FINANCIAL_CLOSE_PASSWORD = "your_secure_password"
```

**Option 2: Environment Variable**

```bash
export FINANCIAL_CLOSE_PASSWORD="your_secure_password"
```

**Graceful Degradation:**

- If `FINANCIAL_CLOSE_PASSWORD` is not configured, the Financial Close tab will display setup instructions
- All other dashboard features work normally without the password configured
- Users can still access all other tabs (Overview, Bank, Invoices, etc.)

## Running the Dashboard

```bash
streamlit run lab_dashboard.py
```

## Financial Close Features

The Financial Close tab provides:

1. **Period Selection**: Choose year, month, and entity
2. **Key Financial Metrics**: Revenue, costs, profit/loss with month-over-month comparison
3. **Validation Checks**:
   - Balance verification (Debit = Credit)
   - Unposted journal entries detection
   - Unpaid invoices identification
   - Old receivables (>90 days) flagging
4. **Trend Analysis**: 6-month trend visualization
5. **Attention Items**: Highlighted discrepancies and items requiring action
6. **Export Options**: JSON, CSV, and TXT report downloads

## Security Notes

- The Financial Close password is stored in Streamlit secrets or environment variables
- Password verification happens on the server side
- Session-based authentication (cleared on page refresh)
- No passwords are stored in browser local storage

## File Structure

```
LAB2/
├── lab_dashboard.py    # Main application
├── requirements.txt    # Python dependencies
├── README.md          # This file
└── .streamlit/        # Configuration directory (create if needed)
    └── secrets.toml   # Secrets configuration (not in git)
```

## Version History

- **v12**: Added Financial Close (Maandafsluiting) tab with password protection
- **v11**: Added AI Chatbot with OpenAI GPT-4
- **v10**: Balance sheet quadrant format, intercompany filtering
- **v9**: Customer map, product analysis
- **v8**: Cashflow forecast, invoice drill-down

## Support

For issues or feature requests, contact the LAB Groep IT team.
