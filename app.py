import streamlit as st
import stripe

# --- 1. App Configuration & Auth ---
st.set_page_config(page_title="Stripe Link Generator", page_icon="💳")
st.title("💳 Payment Link Generator")

# Load API Key
try:
    stripe.api_key = st.secrets["STRIPE_API_KEY"]
except FileNotFoundError:
    st.error("API Key not found. Please set it in .streamlit/secrets.toml")
    st.stop()

# --- 2. Helper Functions ---
@st.cache_data(ttl=300)
def get_active_products():
    """Fetch active prices with product details"""
    try:
        # Fetch prices and expand product data
        prices = stripe.Price.list(active=True, limit=50, expand=['data.product'])
        
        product_options = {}
        for p in prices.data:
            # We store the amount (e.g., 50.00) and currency separately to do math later
            amount = p.unit_amount / 100 if p.unit_amount else 0
            currency = p.currency.upper()
            product_name = p.product.name if hasattr(p.product, 'name') else "Unknown Product"
            
            # Key for the dropdown
            label = f"{product_name} ({amount} {currency})"
            
            # Value stored: A dictionary with ID and Raw Amount
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
    try:
        # 1. Prepare base arguments
        session_args = {
            'customer': customer_id,
            'line_items': [{'price': price_id, 'quantity': 1}],
            'mode': 'payment',
            'success_url': 'https://example.com/success',
        }

        # 2. If there is a discount, create a one-time coupon and attach it
        if discount_percent > 0:
            coupon = stripe.Coupon.create(
                percent_off=discount_percent,
                duration='once',
                name=f"{discount_percent}% Off (CSM Generated)"
            )
            session_args['discounts'] = [{'coupon': coupon.id}]

        # 3. Create Session
        session = stripe.checkout.Session.create(**session_args)
        return session.url
    except Exception as e:
        return f"Error: {str(e)}"

def create_new_customer(email, name):
    try:
        return stripe.Customer.create(email=email, name=name).id
    except Exception as e:
        return None

# --- 3. Main Interface ---

product_map = get_active_products()

if not product_map:
    st.warning("No active products found.")
    st.stop()

# Layout: Sidebar for common settings like Discount
with st.sidebar:
    st.header("Price Settings")
    # Discount Slider (0 to 100%)
    discount = st.number_input("Discount Percentage (%)", min_value=0, max_value=100, value=0, step=5)

tab1, tab2 = st.tabs(["Search / Existing Customer", "Create New Customer"])

# === TAB 1: EXISTING CUSTOMER ===
with tab1:
    st.subheader("Existing Customer")
    existing_cus_id = st.text_input("Customer ID (e.g., cus_1234)")
    
    # Select Product
    selected_label_1 = st.selectbox("Select Product", options=product_map.keys(), key="sel1")
    
    # --- Live Price Calculation ---
    if selected_label_1:
        # Get data from our map
        prod_data = product_map[selected_label_1]
        original_price = prod_data['amount']
        currency = prod_data['currency']
        
        # Calculate new price
        final_price = original_price * (1 - (discount / 100))
        
        # Display the math to the CSM
        st.caption(f"Original: {original_price} {currency}")
        if discount > 0:
            st.metric(label="Final Price to Customer", value=f"{final_price:.2f} {currency}", delta=f"-{discount}%")
        else:
            st.metric(label="Final Price", value=f"{original_price} {currency}")

    if st.button("Generate Link (Existing)"):
        if existing_cus_id and selected_label_1:
            price_id = product_map[selected_label_1]['id']
            link = create_checkout_session(existing_cus_id, price_id, discount)
            if "Error" in link:
                st.error(link)
            else:
                st.success("Link Created!")
                st.code(link, language="text")

# === TAB 2: NEW CUSTOMER ===
with tab2:
    st.subheader("New Customer")
    col1, col2 = st.columns(2)
    with col1:
        new_email = st.text_input("Email")
    with col2:
        new_name = st.text_input("Name")
    
    selected_label_2 = st.selectbox("Select Product", options=product_map.keys(), key="sel2")
    
    # --- Live Price Calculation ---
    if selected_label_2:
        prod_data = product_map[selected_label_2]
        original_price = prod_data['amount']
        currency = prod_data['currency']
        final_price = original_price * (1 - (discount / 100))
        
        if discount > 0:
            st.metric(label="Final Price to Customer", value=f"{final_price:.2f} {currency}", delta=f"-{discount}%")
    
    if st.button("Create & Generate"):
        if new_email and new_name and selected_label_2:
            price_id = product_map[selected_label_2]['id']
            with st.spinner("Processing..."):
                new_id = create_new_customer(new_email, new_name)
                if new_id:
                    link = create_checkout_session(new_id, price_id, discount)
                    st.success(f"Customer created: {new_id}")
                    st.code(link, language="text")
                else:
                    st.error("Failed to create customer.")