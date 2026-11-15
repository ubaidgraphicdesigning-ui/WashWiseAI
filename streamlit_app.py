from __future__ import annotations

import hmac
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from supabase import Client, create_client

from washwise_core import clean_order_items, format_pkr, to_decimal

APP_NAME = "WashWise AI"
PK_TZ = ZoneInfo("Asia/Karachi")
STATUSES = ["received", "inspection", "washing", "ironing", "ready", "out_for_delivery", "delivered", "cancelled"]
STATUS_LABELS = {
    "received": "Order received", "inspection": "Inspection", "washing": "Washing",
    "ironing": "Ironing & finishing", "ready": "Ready for collection",
    "out_for_delivery": "Out for delivery", "delivered": "Delivered", "cancelled": "Cancelled",
}

st.set_page_config(page_title=APP_NAME, page_icon="🧺", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700;800&display=swap');
.stApp{background:#F5F8FC;font-family:'DM Sans',sans-serif}
h1,h2,h3{font-family:Manrope,sans-serif;color:#10243A}
[data-testid="stSidebar"]{background:#10243A}
[data-testid="stSidebar"] *{color:#ECF3FC}
.ww-hero{padding:26px;border-radius:20px;background:linear-gradient(120deg,#10243A,#163F62,#116B72);color:white;margin-bottom:18px}
.ww-hero h1{color:white!important;margin:0}
.ww-hero p{color:#D2E4F5;margin-bottom:0}
div[data-testid="stMetric"]{background:white;border:1px solid #E2EAF2;border-radius:14px;padding:14px}
.stButton>button{border-radius:10px;font-weight:700}
</style>
""", unsafe_allow_html=True)


def secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, "")
        return str(value).strip() if value else default
    except Exception:
        return default


@st.cache_resource
def db_client(url: str, key: str) -> Client:
    return create_client(url, key)


def get_db() -> Client:
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_SECRET_KEY") or secret("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        st.error("Supabase is not configured.")
        st.info("Copy .streamlit/secrets.toml.example to .streamlit/secrets.toml and add your Project URL, Secret key and Staff PIN.")
        st.stop()
    return db_client(url, key)


def money(value: Any, business: dict) -> str:
    return format_pkr(value or 0, business.get("currency", "PKR"))


def get_business(db: Client) -> dict | None:
    query = db.table("businesses").select("*").eq("is_active", True)
    business_id = secret("BUSINESS_ID")
    if business_id:
        query = query.eq("id", business_id)
    rows = query.limit(1).execute().data or []
    return rows[0] if rows else None


def staff_ok() -> bool:
    return bool(st.session_state.get("staff_unlocked"))


def require_staff() -> bool:
    if not staff_ok():
        st.warning("This section requires Staff Workspace access. Enter the Staff PIN in the sidebar.")
        return False
    return True


def setup_page(db: Client) -> None:
    st.markdown('<div class="ww-hero"><h1>Set up WashWise AI</h1><p>Connect your real laundry business to begin.</p></div>', unsafe_allow_html=True)
    pin = st.text_input("Staff PIN", type="password", key="setup_pin")
    if not hmac.compare_digest(pin.encode(), secret("ADMIN_PIN").encode()) or not secret("ADMIN_PIN"):
        st.caption("Enter the Staff PIN configured in Streamlit Secrets to create the first business profile.")
        return
    with st.form("business_setup"):
        name = st.text_input("Business name")
        phone = st.text_input("Business phone")
        email = st.text_input("Business email (optional)")
        address = st.text_area("Business address")
        submitted = st.form_submit_button("Create business profile", type="primary")
    if submitted:
        if not name.strip() or not phone.strip() or not address.strip():
            st.error("Business name, phone and address are required.")
            return
        row = {"business_name": name.strip(), "phone": phone.strip(), "email": email.strip() or None,
               "address": address.strip(), "currency": "PKR", "timezone": "Asia/Karachi", "is_active": True}
        db.table("businesses").insert(row).execute()
        st.success("Business profile created. Refreshing…")
        st.rerun()


def public_services(db: Client, business: dict) -> None:
    st.subheader("Our Services")
    rows = db.table("services").select("name,unit,unit_price").eq("business_id", business["id"]).eq("is_active", True).order("name").execute().data or []
    if rows:
        st.dataframe(pd.DataFrame([{"Service": x["name"], "Pricing unit": x["unit"], "Price": money(x["unit_price"], business)} for x in rows]), use_container_width=True, hide_index=True)
    else:
        st.info("Services will appear here once the business adds its catalogue.")


def track_order(db: Client, business: dict) -> None:
    st.subheader("Track Your Order")
    with st.form("track_form"):
        order_no = st.text_input("Order number", placeholder="WW-YYMMDD-XXXXXX")
        phone_last4 = st.text_input("Last 4 digits of registered phone number", max_chars=4)
        submitted = st.form_submit_button("Track order")
    if submitted:
        rows = db.table("orders").select("id,order_no,status,received_at,due_at").eq("business_id", business["id"]).eq("order_no", order_no.strip().upper()).limit(1).execute().data or []
        if not rows:
            st.error("We could not verify this order. Check the order number and phone digits.")
            return
        order = rows[0]
        customer = db.table("customers").select("phone").eq("business_id", business["id"]).eq("id", db.table("orders").select("customer_id").eq("id", order["id"]).single().execute().data["customer_id"]).single().execute().data
        stored = "".join(ch for ch in str(customer.get("phone", "")) if ch.isdigit())
        supplied = "".join(ch for ch in phone_last4 if ch.isdigit())
        if len(supplied) != 4 or len(stored) < 4 or not hmac.compare_digest(stored[-4:], supplied):
            st.error("We could not verify this order. Check the order number and phone digits.")
            return
        st.success(f"Order {order['order_no']} — {STATUS_LABELS.get(order['status'], order['status'])}")
        if order.get("due_at"):
            st.caption(f"Estimated due: {order['due_at']}")


def staff_sidebar() -> None:
    with st.sidebar:
        st.markdown("## 🧺 WashWise AI")
        st.caption("LAUNDRY OPERATIONS PLATFORM")
        with st.expander("Staff Workspace", expanded=not staff_ok()):
            pin = st.text_input("Staff PIN", type="password", key="staff_pin")
            if st.button("Unlock staff workspace", use_container_width=True):
                expected = secret("ADMIN_PIN")
                if expected and hmac.compare_digest(pin.encode(), expected.encode()):
                    st.session_state.staff_unlocked = True
                    st.success("Staff workspace unlocked.")
                    st.rerun()
                else:
                    st.error("Incorrect Staff PIN.")
            if staff_ok() and st.button("Lock staff workspace", use_container_width=True):
                st.session_state.staff_unlocked = False
                st.rerun()
        pages = ["Overview", "Services", "Track an Order"]
        if staff_ok():
            pages += ["New Order", "Orders & Processing", "Customers", "Payments", "Inventory", "Expenses", "Reports & AI", "Business Settings"]
        return st.radio("Navigation", pages, label_visibility="collapsed")


def overview(db: Client, business: dict) -> None:
    st.markdown(f'<div class="ww-hero"><h1>{business["business_name"]}</h1><p>Smart laundry. Smarter business. · {business.get("address","")}</p></div>', unsafe_allow_html=True)
    orders = db.table("orders").select("id,status,total,paid,created_at").eq("business_id", business["id"]).execute().data or []
    c1, c2, c3 = st.columns(3)
    c1.metric("Total orders", len(orders))
    c2.metric("Payments collected", money(sum(float(x.get("paid") or 0) for x in orders), business))
    c3.metric("Active orders", sum(x.get("status") not in ("delivered", "cancelled") for x in orders))
    st.caption("Live business figures from the connected Supabase database. No sample data is shown.")
    if staff_ok() and orders:
        st.dataframe(pd.DataFrame(orders), use_container_width=True, hide_index=True)


def new_order(db: Client, business: dict) -> None:
    if not require_staff(): return
    st.subheader("Create New Order")
    services = db.table("services").select("*").eq("business_id", business["id"]).eq("is_active", True).order("name").execute().data or []
    if not services:
        st.warning("Add at least one service in Business Settings before creating orders.")
        return
    with st.form("new_order"):
        customer_name = st.text_input("Customer name")
        customer_phone = st.text_input("Customer phone")
        customer_address = st.text_area("Customer address (optional)")
        garment = st.text_input("Garment / item", placeholder="Shirt")
        service_name = st.selectbox("Service", [x["name"] for x in services])
        selected = next(x for x in services if x["name"] == service_name)
        qty = st.number_input("Quantity", min_value=0.1, value=1.0, step=1.0)
        price = st.number_input("Unit price (PKR)", min_value=0.0, value=float(selected["unit_price"]), step=10.0)
        due_date = st.date_input("Due date", value=date.today() + timedelta(days=2))
        notes = st.text_area("Order notes")
        submitted = st.form_submit_button("Create order", type="primary")
    if submitted:
        try:
            items = clean_order_items([{"garment_name": garment, "service_name": service_name, "service_id": selected["id"], "quantity": qty, "unit_price": price}])
            result = db.rpc("ww_create_order", {"p_business_id": business["id"], "p_customer_name": customer_name.strip(),
                "p_customer_phone": customer_phone.strip(), "p_customer_address": customer_address.strip(),
                "p_due_at": datetime.combine(due_date, time(18, 0), PK_TZ).isoformat(),
                "p_items": items, "p_notes": notes.strip() or None}).execute().data
            if isinstance(result, list): result = result[0]
            st.success(f"Order created: {result['order_no']} · {money(result['total'], business)}")
        except Exception as exc:
            st.error(f"Could not create order: {exc}")


def orders_page(db: Client, business: dict) -> None:
    if not require_staff(): return
    st.subheader("Orders & Processing")
    rows = db.table("orders").select("*").eq("business_id", business["id"]).order("created_at", desc=True).limit(500).execute().data or []
    if not rows:
        st.info("No orders have been entered yet.")
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    order_no = st.selectbox("Select order", [x["order_no"] for x in rows])
    order = next(x for x in rows if x["order_no"] == order_no)
    with st.form("status_update"):
        status = st.selectbox("New status", STATUSES, index=STATUSES.index(order["status"]))
        note = st.text_input("Status note")
        save = st.form_submit_button("Update order status")
    if save:
        db.rpc("ww_update_order_status", {"p_business_id": business["id"], "p_order_id": order["id"], "p_new_status": status, "p_note": note}).execute()
        st.success("Order status updated.")
        st.rerun()


def customers_page(db: Client, business: dict) -> None:
    if not require_staff(): return
    st.subheader("Customers")
    rows = db.table("customers").select("full_name,phone,email,address,created_at").eq("business_id", business["id"]).order("created_at", desc=True).execute().data or []
    if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else: st.info("No customers recorded yet. Customers are added when staff creates an order.")


def payments_page(db: Client, business: dict) -> None:
    if not require_staff(): return
    st.subheader("Record Payment")
    orders = db.table("orders").select("id,order_no,total,paid").eq("business_id", business["id"]).order("created_at", desc=True).execute().data or []
    open_orders = [x for x in orders if float(x["total"]) > float(x["paid"])]
    if not open_orders:
        st.info("There are no outstanding order balances.")
        return
    with st.form("payment_form"):
        chosen = st.selectbox("Order", open_orders, format_func=lambda x: f'{x["order_no"]} · Balance {money(float(x["total"])-float(x["paid"]), business)}')
        amount = st.number_input("Payment amount (PKR)", min_value=0.01, max_value=float(chosen["total"])-float(chosen["paid"]), value=min(100.0, float(chosen["total"])-float(chosen["paid"])))
        method = st.selectbox("Payment method", ["Cash", "Bank transfer", "Card", "Other"])
        reference = st.text_input("Reference (optional)")
        submitted = st.form_submit_button("Save payment")
    if submitted:
        db.rpc("ww_record_payment", {"p_business_id": business["id"], "p_order_id": chosen["id"], "p_amount": float(to_decimal(amount)), "p_method": method, "p_reference": reference or None}).execute()
        st.success("Payment recorded.")
        st.rerun()


def inventory_page(db: Client, business: dict) -> None:
    if not require_staff(): return
    st.subheader("Inventory")
    with st.form("inventory_add"):
        name = st.text_input("Item name")
        unit = st.selectbox("Unit", ["piece", "kg", "litre", "pack", "bottle"])
        opening = st.number_input("Opening quantity", min_value=0.0, value=0.0)
        reorder = st.number_input("Reorder level", min_value=0.0, value=2.0)
        submitted = st.form_submit_button("Add inventory item")
    if submitted:
        db.table("inventory_items").insert({"business_id": business["id"], "item_name": name.strip(), "unit": unit, "quantity_on_hand": opening, "reorder_level": reorder}).execute()
        st.success("Inventory item added.")
        st.rerun()
    rows = db.table("inventory_items").select("*").eq("business_id", business["id"]).eq("is_active", True).order("item_name").execute().data or []
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        item = st.selectbox("Stock adjustment item", rows, format_func=lambda x: x["item_name"])
        delta = st.number_input("Quantity change (+ in / - out)", value=1.0)
        note = st.text_input("Movement note")
        if st.button("Save stock movement"):
            db.rpc("ww_adjust_inventory", {"p_business_id": business["id"], "p_item_id": item["id"], "p_quantity_change": delta, "p_note": note}).execute()
            st.success("Stock updated.")
            st.rerun()


def expenses_page(db: Client, business: dict) -> None:
    if not require_staff(): return
    st.subheader("Business Expenses")
    with st.form("expense_form"):
        category = st.selectbox("Category", ["Rent", "Utilities", "Supplies", "Payroll", "Delivery", "Maintenance", "Other"])
        amount = st.number_input("Amount (PKR)", min_value=0.01, value=100.0)
        expense_date = st.date_input("Expense date", value=date.today())
        description = st.text_input("Description")
        submitted = st.form_submit_button("Save expense")
    if submitted:
        db.table("expenses").insert({"business_id": business["id"], "category": category, "amount": float(to_decimal(amount)), "expense_date": expense_date.isoformat(), "description": description.strip()}).execute()
        st.success("Expense saved.")
        st.rerun()
    rows = db.table("expenses").select("*").eq("business_id", business["id"]).order("expense_date", desc=True).execute().data or []
    if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def reports_page(db: Client, business: dict) -> None:
    if not require_staff(): return
    st.subheader("Reports & AI Insights")
    orders = db.table("orders").select("id,status,total,paid,created_at").eq("business_id", business["id"]).execute().data or []
    expenses = db.table("expenses").select("amount,expense_date").eq("business_id", business["id"]).execute().data or []
    total_paid = sum(float(x.get("paid") or 0) for x in orders)
    total_expenses = sum(float(x.get("amount") or 0) for x in expenses)
    a, b, c = st.columns(3)
    a.metric("Orders", len(orders)); b.metric("Collected", money(total_paid, business)); c.metric("Recorded expenses", money(total_expenses, business))
    st.caption("Cash movement is collections minus recorded expenses, not audited accounting profit.")
    if orders: st.download_button("Download orders CSV", pd.DataFrame(orders).to_csv(index=False).encode("utf-8-sig"), "washwise_orders.csv", "text/csv")
    question = st.text_input("Ask about your recorded business data")
    if st.button("Generate AI insight", disabled=not question.strip()):
        api_key = secret("GEMINI_API_KEY")
        if not api_key:
            st.info(f"Current records: {len(orders)} orders, {money(total_paid, business)} collected and {money(total_expenses, business)} expenses. Add a Gemini API key in private Streamlit Secrets to enable AI explanations.")
        else:
            try:
                from google import genai
                model = secret("GEMINI_MODEL", "gemini-2.5-flash")
                client = genai.Client(api_key=api_key)
                prompt = f"You are a laundry operations analyst. Answer using only these aggregated figures; do not invent details. Orders: {len(orders)}; collections: {total_paid}; expenses: {total_expenses}. Question: {question}"
                answer = client.models.generate_content(model=model, contents=prompt)
                st.write(answer.text or "No response returned.")
            except Exception as exc:
                st.error(f"AI request failed: {exc}")


def settings_page(db: Client, business: dict) -> None:
    if not require_staff(): return
    st.subheader("Business Settings & Service Catalogue")
    with st.form("profile"):
        name = st.text_input("Business name", business.get("business_name", ""))
        phone = st.text_input("Business phone", business.get("phone", ""))
        email = st.text_input("Email", business.get("email") or "")
        address = st.text_area("Address", business.get("address", ""))
        save = st.form_submit_button("Save business profile")
    if save:
        db.table("businesses").update({"business_name": name.strip(), "phone": phone.strip(), "email": email.strip() or None, "address": address.strip()}).eq("id", business["id"]).execute()
        st.success("Business profile saved.")
        st.rerun()
    st.divider()
    with st.form("service_add"):
        service = st.text_input("Service name")
        unit = st.selectbox("Pricing unit", ["piece", "kg", "pair", "item", "suit", "dozen"])
        price = st.number_input("Unit price (PKR)", min_value=0.0, value=0.0, step=10.0)
        add = st.form_submit_button("Add service")
    if add:
        if not service.strip() or price <= 0:
            st.error("Enter a service name and a price greater than zero.")
        else:
            db.table("services").insert({"business_id": business["id"], "name": service.strip(), "unit": unit, "unit_price": float(to_decimal(price)), "is_active": True}).execute()
            st.success("Service added.")
            st.rerun()
    rows = db.table("services").select("*").eq("business_id", business["id"]).order("name").execute().data or []
    if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def main() -> None:
    db = get_db()
    business = get_business(db)
    if not business:
        setup_page(db)
        return
    page = staff_sidebar()
    if page == "Overview": overview(db, business)
    elif page == "Services": public_services(db, business)
    elif page == "Track an Order": track_order(db, business)
    elif page == "New Order": new_order(db, business)
    elif page == "Orders & Processing": orders_page(db, business)
    elif page == "Customers": customers_page(db, business)
    elif page == "Payments": payments_page(db, business)
    elif page == "Inventory": inventory_page(db, business)
    elif page == "Expenses": expenses_page(db, business)
    elif page == "Reports & AI": reports_page(db, business)
    elif page == "Business Settings": settings_page(db, business)
    st.sidebar.divider()
    st.sidebar.caption(f"{APP_NAME} · Pakistan Standard Time · {datetime.now(PK_TZ):%d %b %Y %I:%M %p}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        st.error("The application could not complete this request.")
        st.exception(exc)
        st.caption("Check Supabase connection, schema migration and private Streamlit Secrets.")
