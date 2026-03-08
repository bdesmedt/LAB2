/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, xml } from "@odoo/owl";

const DASHBOARD_URL = "https://z3cz42wywpc5tddblzs8qn.streamlit.app/";

class LabDashboard extends Component {
    static template = xml`
        <div class="o_lab_dashboard" style="
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            display: flex;
            flex-direction: column;
        ">
            <iframe
                t-att-src="dashboardUrl"
                style="
                    flex: 1;
                    width: 100%;
                    border: none;
                    display: block;
                "
                allow="fullscreen"
                title="LAB Financieel Dashboard"
            />
        </div>
    `;

    get dashboardUrl() {
        return DASHBOARD_URL;
    }
}

registry.category("actions").add("lab_financial_dashboard.Dashboard", LabDashboard);
