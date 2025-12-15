import streamlit as st
import stripe

# --- 1. Password Protection ---
def check_password():
    """Returns `True` if the user had the correct password."""
    try:
        actual_password = st.secrets["APP_PASSWORD"] 
    except (FileNotFoundError, KeyError):
        st.error("Secrets not found. Please add APP_PASSWORD to secrets.")
        return False

    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    st.text_input(
        "Enter Team Password", 
        type="password", 
        on_change=password_entered, 
        key="password_input"
    )
    
    if "password_error" in st.session_state:
        st.error(st.session_state.password_error)
        
    return False

def password_entered():
    if st.session_state["password_input"] == st.secrets["APP_PASSWORD"]:
        st.session_state.password_correct = True
        if "password_error" in st.session_state:
            del st.session_state.password_error
    else:
        st.session_state.password_correct = False
        st.session_state.password_error = "😕 Password incorrect"

# STOP APP IF PASSWORD WRONG
if not check_password():
    st.stop()

# --- 2. App Configuration & Auth ---
st.set_page_config(page_title="Stripe Link Generator", page_icon="💳")
st.title("💳 Payment Link Generator")

try:
    stripe.api_key = st.secrets["STRIPE_API_KEY"]
except KeyError:
    st.error("STRIPE_API_KEY not found. Check your Advanced Settings.")
    st.stop()

# --- 3. Helper Functions ---
@st.cache_data(ttl=300)
def get_active_products():
    """Fetch active prices with product details"""
    try:
        prices = stripe.Price.list(active=True, limit=50, expand=['data.product'])
        product_options = {}
        for p in prices.data:
            amount = p.unit_amount / 100 if p.unit_amount else 0
            currency = p.currency.upper()
            product_name = p.product.name if hasattr(p.product, 'name') else "Unknown Product"
            label = f"{product_name} ({amount} {currency})"
            product_options[label] = {
                "id": p.id,
                "amount": amount,
                "currency": currency
            }
        return product_options
    except Exception as e:
        st.error(f"Error connecting to Stripe: {e}")
        return {}

def create_checkout_session(customer_id, price_id, discount_percent=0):
    """
    Creates the session. 
    FIX: Removed 'customer_email' to avoid conflict with 'customer'.
    """
    try:
        session_args = {
            'customer': customer_id,
            'line_items': [{'price': price_id, 'quantity': 1}],
            'mode': 'payment',
            'success_url': 'https://example.com/success',
            # This prevents the user from changing their address/name easily
            'customer_update': {'name': 'auto', 'address': 'auto'}, 
        }

        # Apply Discount
        if discount_percent > 0:
            coupon = stripe.Coupon.create(
                percent_off=discount_percent,
                duration='once',
                name=f"{discount_percent}% Off (CSM Generated)"
            )
            session_args['discounts'] = [{'coupon': coupon.id}]

        session = stripe.checkout.Session.create(**session_args)
        return session.url
    except Exception as e:
        return f"Error: {str(e)}"

def get_or_create_customer(email, name):
    """
    Checks if customer exists by email to prevent duplicates.
    Returns: (id, is_duplicate_boolean)
    """
    try:
        # 1. Check for duplicates
        search = stripe.Customer.list(email=email, limit=1)
        if search.data:
            return search.data[0].id, True
        
        # 2. Create new if not found
        new_cus = stripe.Customer.create(email=email, name=name)
        return new_cus.id, False
    except Exception as e:
        return None, False

# --- 4. Main Interface ---

product_map = get_active_products()

if not product_map:
    st.warning("No active products found in Stripe account.")
    st.stop()

# Sidebar for common settings
with st.sidebar:
    st.header("Price Settings")
    discount = st.number_input("Discount Percentage (%)", min_value=0, max_value=100, value=0, step=5)

tab1, tab2 = st.tabs(["Search / Existing Customer", "Create New Customer"])

# === TAB 1: EXISTING CUSTOMER ===
with tab1:
    st.subheader("Existing Customer")
    existing_cus_id = st.text_input("Customer ID (e.g., cus_1234)")
    selected_label_1 = st.selectbox("Select Product", options=product_map.keys(), key="sel1")
    
    # Live Math Display
    if selected_label_1:
        prod_data = product_map[selected_label_1]
        final_price = prod_data['amount'] * (1 - (discount / 100))
        if discount > 0:
            st.metric("Final Price", f"{final_price:.2f} {prod_data['currency']}", f"-{discount}%")
        else:
            st.metric("Price", f"{prod_data['amount']} {prod_data['currency']}")

    if st.button("Generate Link (Existing)"):
        if existing_cus_id and selected_label_1:
            price_id = product_map[selected_label_1]['id']
            link = create_checkout_session(existing_cus_id, price_id, discount)
            if "Error" in link:
                st.error(link)
            else:
                st.success("Link Created!")
                st.code(link, language="text")

# === TAB 2: NEW CUSTOMER (With Duplicate Check) ===
with tab2:
    st.subheader("New Customer")
    col1, col2 = st.columns(2)
    with col1:
        new_email = st.text_input("Email")
    with col2:
        new_name = st.text_input("Name")
    
    selected_label_2 = st.selectbox("Select Product", options=product_map.keys(), key="sel2")
    
    # Live Math Display
    if selected_label_2:
        prod_data = product_map[selected_label_2]
        final_price = prod_data['amount'] * (1 - (discount / 100))
        if discount > 0:
            st.metric("Final Price", f"{final_price:.2f} {prod_data['currency']}", f"-{discount}%")

    if st.button("Create & Generate"):
        if new_email and new_name and selected_label_2:
            price_id = product_map[selected_label_2]['id']
            with st.spinner("Checking database..."):
                
                # Check for duplicate / Create
                cus_id, is_duplicate = get_or_create_customer(new_email, new_name)
                
                if cus_id:
                    if is_duplicate:
                        # Fixed the Syntax Error here by adding the f"..." correctly
                        st.warning(f"⚠️ Account exists! Using existing ID: {cus_id}")
                    else:
                        st.success(f"✅ New Customer created: {cus_id}")
                    
                    # Generate the link using the ID
                    link = create_checkout_session(cus_id, price_id, discount)
                    if "Error" in link:
                        st.error(link)
                    else:
                        st.code(link, language="text")
                else:
                    st.error("Failed to process customer (API Error).")