import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

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

            st.markdown("### 📈 Select Metric(s) to Plot Against Function Name")
            selected_metrics = st.multiselect("Select Metrics", options=metric_columns, default=[metric_columns[0]])

            st.markdown("### 🔍 Filter by Lambda Functions (Optional)")
            function_options = sorted(df["Function Name"].unique().tolist())

            # Allow the user to select multiple functions for comparison
            selected_functions = st.multiselect("Select Lambda Functions for Comparison", options=function_options, default=function_options)

            if len(selected_functions) == 0:
                st.warning("Please select at least one Lambda function for comparison.")
            else:
                # Filter data for selected functions
                filtered_df = df[df["Function Name"].isin(selected_functions)]

                if filtered_df.empty:
                    st.warning("No data available for the selected functions.")
                else:
                    # Show statistics for selected metric(s)
                    st.markdown("### 🧮 Summary Statistics")
                    summary_stats = filtered_df[selected_metrics].describe().T
                    summary_stats['range'] = summary_stats['max'] - summary_stats['min']
                    st.dataframe(summary_stats)

                    # Plot bar chart with selected functions for comparison
                    for metric in selected_metrics:
                        fig = px.bar(
                            filtered_df,
                            x="Function Name",
                            y=metric,
                            title=f"{metric} by Lambda Function",
                            labels={"Function Name": "Lambda Function", metric: metric},
                            color="Function Name",  # To distinguish different functions by color
                            barmode="group",  # Display bars next to each other for comparison
                            hover_data=["Function Name", metric]  # Show details on hover
                        )
                        st.plotly_chart(fig, use_container_width=True)

                    # Add scatter plot option for comparison
                    if len(selected_metrics) == 2:
                        st.markdown("### 🔄 Scatter Plot for Metric Comparison")
                        scatter_fig = px.scatter(
                            filtered_df,
                            x=selected_metrics[0],
                            y=selected_metrics[1],
                            color="Function Name",
                            title=f"Scatter Plot of {selected_metrics[0]} vs {selected_metrics[1]}",
                            labels={selected_metrics[0]: selected_metrics[0], selected_metrics[1]: selected_metrics[1]},
                            hover_data=["Function Name"]
                        )
                        st.plotly_chart(scatter_fig, use_container_width=True)

                    # Export the filtered data as CSV
                    st.markdown("### 📤 Export Data")
                    csv = filtered_df.to_csv(index=False)
                    st.download_button(
                        label="Download Data as CSV",
                        data=csv,
                        file_name="filtered_lambda_data.csv",
                        mime="text/csv"
                    )

                    # Export the most recent plot as PNG (if desired)
                    st.markdown("### 📷 Export Chart as PNG")
                    export_png_button = st.button("Download Latest Chart as PNG")
                    if export_png_button:
                        fig.write_image("chart.png")
                        st.image("chart.png")

    except Exception as e:
        st.error(f"❌ Error processing file: {e}")

else:
    st.info("👆 Upload the Excel file to begin.")
