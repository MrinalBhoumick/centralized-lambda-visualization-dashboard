import streamlit as st
import pandas as pd
import plotly.express as px

# Page setup
st.set_page_config(page_title="Lambda Report Dashboard", layout="wide")
st.title("🚀 Lambda Insights Dashboard")

# Upload Excel
uploaded_file = st.file_uploader("📂 Upload Excel Report", type=["xlsx"])

@st.cache_data
def load_data(file):
    return pd.read_excel(file)

if uploaded_file:
    try:
        df = load_data(uploaded_file)

        st.subheader("📄 Data Preview")
        st.dataframe(df, use_container_width=True)

        if "Function Name" not in df.columns:
            st.error("❌ The uploaded file must contain a 'Function Name' column.")
        else:
            # Extract metric columns (exclude 'Function Name')
            metric_columns = [col for col in df.columns if col != "Function Name"]

            st.markdown("### 📈 Select a Metric to Plot Against Function Name")
            selected_metric = st.selectbox("Metric", options=metric_columns)

            st.markdown("### 🔍 Filter by Lambda Function (Optional)")
            function_options = ["All Functions"] + sorted(df["Function Name"].unique().tolist())
            selected_function = st.selectbox("Function Name", options=function_options)

            # Apply filter if a specific function is selected
            if selected_function != "All Functions":
                filtered_df = df[df["Function Name"] == selected_function]
            else:
                filtered_df = df

            if filtered_df.empty:
                st.warning("No data available for the selected function.")
            else:
                # Plot bar chart
                fig = px.bar(
                    filtered_df,
                    x="Function Name",
                    y=selected_metric,
                    title=f"{selected_metric} by Function Name",
                    labels={"Function Name": "Lambda Function", selected_metric: selected_metric},
                    color="Function Name"
                )
                st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"❌ Error processing file: {e}")

else:
    st.info("👆 Upload the Excel file to begin.")
