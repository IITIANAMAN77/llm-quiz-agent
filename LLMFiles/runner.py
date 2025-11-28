import pandas as pd
df = pd.read_csv("demo-audio-data.csv", header=None)
cutoff = 47745
filtered_df = df[df[0] > cutoff]
answer = filtered_df[0].sum()
print(answer)