import streamlit as st
import pandas as pd
import io
import re

# --- Page Setup ---
st.set_page_config(page_title="MQ Marketing Expert", layout="wide", page_icon="🚀")
st.title("🚀 MQ Expert: Final Campaign Sync")
st.markdown("### Integrerad: Artikelsynk, Lagervarningar och Strikt Könsisolering")

# --- 1. UTILITIES (Motorn) ---
def clean_numeric(series):
    """Hanterar europeisk formatering: €1.454,95 -> 1454.95"""
    # Ta bort valutasymboler och mellanslag, byt punkt/komma
    s = series.astype(str).str.replace(r'[^\d,\.-]', '', regex=True)
    s = s.str.replace('.', '', regex=False).str.replace(',', '.', regex=False)
    return pd.to_numeric(s, errors='coerce').fillna(0)

def standardize_sku(sku):
    """Förkortar SKU till 13-teckens Config ID (t.ex. S3B21N003-K11)"""
    s = str(sku).strip().upper().replace('.0', '')
    if '-' in s:
        parts = s.split('-')
        if len(parts) >= 2:
            # Returnerar första delen + de 3 första tecknen efter bindestrecket
            return f"{parts[0]}-{parts[1][:3]}"
    return s

def load_csv(file):
    """Identifierar automatiskt separator och kodning för europeiska CSV-filer"""
    if file is None: return None
    raw_data = file.read(40000)
    file.seek(0)
    try: 
        sample = raw_data.decode('utf-8')
        encoding = 'utf-8'
    except: 
        sample = raw_data.decode('latin-1')
        encoding = 'latin-1'
    
    # Detektera om filen använder semikolon eller komma
    sep = ';' if ';' in sample else ','
    file.seek(0)
    return pd.read_csv(file, sep=sep, encoding=encoding)

# --- 2. SIDEBAR: INSTÄLLNINGAR ---
with st.sidebar:
    st.header("📂 Datauppladdning")
    z_marketing = st.file_uploader("1. MQ Weekly SKU Report", type="csv")
    stock_file = st.file_uploader("2. Inventeringsfil (Lagerdata)", type="csv")
    
    st.divider()
    st.header("🏆 TOP Tier Gränsvärden")
    t_stock = st.number_input("Min Lager (TOP)", value=10)
    t_roas = st.number_input("Min ROAS (TOP)", value=4.0)
    
    st.header("🥈 MEDIUM Tier Gränsvärden")
    m_stock = st.number_input("Min Lager (MED)", value=5)
    m_roas = st.number_input("Min ROAS (MED)", value=2.0)

    st.header("⚠️ Lagervarning")
    days_threshold = st.slider("Varning om lager räcker färre än (dagar):", 1, 14, 5)

# --- 3. DATA PROCESSING ---
if z_marketing and stock_file:
    df_m_raw = load_csv(z_marketing)
    df_s_raw = load_csv(stock_file)

    # A. Rensa Marknadsföringsdata & Filtrera på senaste veckan
    # Vi antar att kolumn 0 är 'Year' och kolumn 2 är 'Week' enligt din fil
    df_m = df_m_raw[df_m_raw.iloc[:, 0].astype(str).str.contains('20', na=False)].copy()
    latest_week = clean_numeric(df_m['Week']).max()
    df_m_latest = df_m[clean_numeric(df_m['Week']) == latest_week].copy()
    
    # Generera Artikel-IDn och rensa mätvärden
    # 'Config SKU' är kolumn 6, 'Budget spent' kolumn 7, 'Items sold' kolumn 15, 'GMV' kolumn 16
    df_m_latest['Article'] = df_m_latest['Config SKU'].apply(standardize_sku)
    df_m_latest['GMV_Val'] = clean_numeric(df_m_latest['GMV'])
    df_m_latest['Spend_Val'] = clean_numeric(df_m_latest['Budget spent'])
    df_m_latest['Sold_Val'] = clean_numeric(df_m_latest['Items sold'])
    
    # B. STRIKT KÖNSISOLERING
    def detect_group(row):
        g = str(row).lower()
        if 'dam' in g or 'fem' in g:
            return 'FEMALE'
        return 'MALE_UNISEX_KIDS'
    
    # Använd kolumnen 'Gender' (kolumn 4)
    df_m_latest['Group_Draft'] = df_m_latest['Gender'].apply(detect_group)
    
    # Lås kön per artikel (vissa artiklar kan dyka upp i flera kampanjer)
    gender_lock = df_m_latest.sort_values('Group_Draft').groupby('Article')['Group_Draft'].first().reset_index()

    # C. Aggregera mätvärden till artikelnivå
    df_m_agg = df_m_latest.groupby('Article').agg({
        'GMV_Val': 'sum', 
        'Spend_Val': 'sum', 
        'Sold_Val': 'sum'
    }).reset_index()
    df_m_agg['ROAS_Actual'] = df_m_agg['GMV_Val'] / df_m_agg['Spend_Val'].replace(0, 1)
    
    # Koppla på det låsta könet
    df_m_agg = pd.merge(df_m_agg, gender_lock, on='Article', how='left')

    # D. Hantera Inventeringsdata
    # 'zalando_article_variant' är kolumn 4 i din lagerfil
    df_s_raw['Article'] = df_s_raw['zalando_article_variant'].apply(standardize_sku)
    stock_cols = [c for c in df_s_raw.columns if 'stock' in c.lower()]
    for col in stock_cols:
        df_s_raw[col] = clean_numeric(df_s_raw[col])
    
    df_s_pivot = df_s_raw.groupby('Article')[stock_cols].sum().reset_index()
    df_s_pivot['Total_Stock'] = df_s_pivot[stock_cols].sum(axis=1)

    # E. Merge & Tiering Logik
    df = pd.merge(df_m_agg, df_s_pivot[['Article', 'Total_Stock']], on='Article', how='left').fillna(0)
    
    # Beräkna lagerdagar
    df['Daily_Velocity'] = df['Sold_Val'] / 7
    df['Days_Left'] = df['Total_Stock'] / df['Daily_Velocity'].replace(0, 0.001)

    def assign_tier(row):
        if row['Total_Stock'] >= t_stock and row['ROAS_Actual'] >= t_roas: return 'TOP'
        elif row['Total_Stock'] >= m_stock and row['ROAS_Actual'] >= m_roas: return 'MEDIUM'
        return 'LOW'

    df['Tier'] = df.apply(assign_tier, axis=1)

    # --- 4. DASHBOARD OUTPUT ---
    st.header("📊 MQ Kampanjfördelning")
    
    # Nyckeltal
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Unika Artiklar", len(df))
    m2.metric("Total ROAS", f"{(df['GMV_Val'].sum()/df['Spend_Val'].sum()):.2f}" if df['Spend_Val'].sum() > 0 else "0.0")
    m3.metric("Lagervarningar", len(df[(df['Tier'] == 'TOP') & (df['Days_Left'] < days_threshold) & (df['Sold_Val'] > 0)]))
    m4.metric("Matchat Lager", f"{df['Total_Stock'].sum():,.0f} st")

    # LAGVARNINGSSEKTION
    warnings = df[(df['Tier'] == 'TOP') & (df['Days_Left'] < days_threshold) & (df['Sold_Val'] > 0)]
    if not warnings.empty:
        st.error(f"🔥 LAGERVARNING: {len(warnings)} TOP-artiklar håller på att ta slut!")
        st.dataframe(warnings[['Article', 'Group_Draft', 'Total_Stock', 'Sold_Val', 'Days_Left']].sort_values('Days_Left'), use_container_width=True)

    st.divider()

    # EXPORT-HINKAR
    for group in ['FEMALE', 'MALE_UNISEX_KIDS']:
        st.subheader(f"📂 {group} Tiers")
        cols = st.columns(3)
        for i, tier in enumerate(['TOP', 'MEDIUM', 'LOW']):
            with cols[i]:
                subset = df[(df['Group_Draft'] == group) & (df['Tier'] == tier)]
                skus = subset['Article'].unique().tolist()
                
                st.markdown(f"**{tier} {group}**")
                st.metric("Artiklar", len(skus))
                st.text_area("SKU Lista", ",".join(skus), height=150, key=f"t_{group}_{tier}", label_visibility="collapsed")
                
                csv = pd.DataFrame(skus).to_csv(index=False, header=False).encode('utf-8')
                st.download_button("Exportera CSV", csv, f"MQ_{group}_{tier}.csv", key=f"d_{group}_{tier}")

    # --- 5. INSPEKTÖREN ---
    st.divider()
    with st.expander("🔍 Djupdykning i data"):
        st.dataframe(df[['Article', 'Group_Draft', 'Tier', 'Total_Stock', 'Days_Left', 'ROAS_Actual', 'GMV_Val', 'Spend_Val']], use_container_width=True)

else:
    st.info("👋 Välkommen! Ladda upp MQ Weekly SKU Report och din inventeringsfil för att börja.")