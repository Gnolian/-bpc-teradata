import pandas as pd

df = pd.read_parquet("outputs/perfil_full.parquet")

df.to_excel("perfil_bpc_dashboard.xlsx", index=False)

print("Excel gerado.")