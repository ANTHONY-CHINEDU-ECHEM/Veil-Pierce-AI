# Benchmark results

This document is generated from reports/metrics.json by the commands veilpierce benchmark and veilpierce docs. Every figure is measured against the ground truth of a synthetic registry and describes recovery of planted structure, not performance on a live register.

Seed 7, data snapshot 2026/09/30, configuration fingerprint 3681c04b7099.

## Dataset and graph

<table>
<tr><th>Table</th><th>Rows</th></tr>
<tr><td>companies</td><td>250,000</td></tr>
<tr><td>officers</td><td>391,066</td></tr>
<tr><td>pscs</td><td>240,932</td></tr>
<tr><td>offshore entities</td><td>62,551</td></tr>
<tr><td>offshore officers</td><td>56,613</td></tr>
<tr><td>offshore edges</td><td>67,060</td></tr>
<tr><td>sanctions</td><td>1,500</td></tr>
<tr><td>total</td><td>1,069,722</td></tr>
</table>

<table>
<tr><th>Node kind</th><th>Nodes</th></tr>
<tr><td>company</td><td>250,000</td></tr>
<tr><td>person</td><td>152,837</td></tr>
<tr><td>address</td><td>114,086</td></tr>
<tr><td>offshore</td><td>62,551</td></tr>
<tr><td>leak officer</td><td>56,476</td></tr>
<tr><td>foreign</td><td>1,831</td></tr>
<tr><td>sanction</td><td>1,500</td></tr>
<tr><td>total</td><td>639,281</td></tr>
</table>

<table>
<tr><th>Edge type</th><th>Edges</th></tr>
<tr><td>officer of</td><td>391,066</td></tr>
<tr><td>registered at</td><td>250,000</td></tr>
<tr><td>controls</td><td>228,524</td></tr>
<tr><td>leak officer of</td><td>56,613</td></tr>
<tr><td>leak shareholder of</td><td>10,447</td></tr>
<tr><td>sanctions match</td><td>335</td></tr>
<tr><td>total</td><td>936,985</td></tr>
</table>

<table>
<tr><th>Planted typology</th><th>Companies</th></tr>
<tr><td>Nominee director network</td><td>6,157</td></tr>
<tr><td>Mass registration address</td><td>12,195</td></tr>
<tr><td>Circular ownership</td><td>1,296</td></tr>
<tr><td>Sanctions proximity</td><td>309</td></tr>
<tr><td>Opaque offshore ownership</td><td>7,407</td></tr>
<tr><td>Burst incorporation and phoenix activity</td><td>2,467</td></tr>
<tr><td>any typology</td><td>19,660</td></tr>
<tr><td>two or more typologies</td><td>8,255</td></tr>
</table>

<table>
<tr><th>Benign lookalike</th><th>Companies</th></tr>
<tr><td>benign agent</td><td>14,608</td></tr>
<tr><td>group tree</td><td>11,735</td></tr>
<tr><td>professional director</td><td>5,627</td></tr>
<tr><td>foreign parent</td><td>1,375</td></tr>
<tr><td>spv batch</td><td>1,060</td></tr>
<tr><td>namesake</td><td>334</td></tr>
</table>

## Entity resolution

<table>
<tr><th>Method</th><th>Pairwise precision</th><th>Pairwise recall</th><th>F1</th><th>Identities produced</th></tr>
<tr><td>Exact name and birth month</td><td>1.000</td><td>0.336</td><td>0.503</td><td>320,104</td></tr>
<tr><td>Entity resolution</td><td>0.991</td><td>0.982</td><td>0.987</td><td>152,837</td></tr>
</table>

The registry holds 598,210 person records for 154,202 true persons.

<table>
<tr><th>Corporate controller resolved by</th><th>Records</th><th>Accuracy</th></tr>
<tr><td>exact name</td><td>3,353</td><td>1.000</td></tr>
<tr><td>fuzzy name</td><td>122</td><td>1.000</td></tr>
<tr><td>fuzzy name and jurisdiction</td><td>2</td><td>1.000</td></tr>
<tr><td>name and jurisdiction</td><td>3,932</td><td>1.000</td></tr>
<tr><td>name without legal form</td><td>156</td><td>1.000</td></tr>
<tr><td>registration number</td><td>9,379</td><td>1.000</td></tr>
<tr><td>unresolved stub</td><td>4,436</td><td>0.999</td></tr>
<tr><td>all methods</td><td>21,380</td><td>0.9998</td></tr>
</table>

<table>
<tr><th>Address measure</th><th>Value</th></tr>
<tr><td>Planted shared addresses</td><td>48</td></tr>
<tr><td>Mean spellings of one address in the raw data</td><td>152.0</td></tr>
<tr><td>Share of companies gathered under the largest raw spelling</td><td>0.140</td></tr>
<tr><td>Share of companies gathered after address resolution</td><td>1.000</td></tr>
<tr><td>UK companies named as shareholders in leak data and tied back to the register</td><td>137 of 137</td></tr>
</table>

## Sanctions screening

<table>
<tr><th>How the listed party appears</th><th>Parties</th><th>Found</th><th>Found as match</th><th>Found as review</th></tr>
<tr><td>leak officer</td><td>85</td><td>1.000</td><td>0.000</td><td>1.000</td></tr>
<tr><td>offshore entity</td><td>38</td><td>1.000</td><td>1.000</td><td>0.000</td></tr>
<tr><td>registry person</td><td>65</td><td>0.892</td><td>0.677</td><td>0.215</td></tr>
</table>

<table>
<tr><th>Alert tier</th><th>Alerts</th><th>True</th><th>Precision</th></tr>
<tr><td>match</td><td>97</td><td>82</td><td>0.845</td></tr>
<tr><td>review</td><td>238</td><td>99</td><td>0.416</td></tr>
</table>

<table>
<tr><th>Control steps from the listed party</th><th>Exposed companies</th><th>Recall</th></tr>
<tr><td>1</td><td>103</td><td>0.932</td></tr>
<tr><td>2</td><td>135</td><td>0.978</td></tr>
<tr><td>3</td><td>60</td><td>0.983</td></tr>
<tr><td>4</td><td>11</td><td>1.000</td></tr>
</table>

## Detection by typology

<table>
<tr><th>Typology</th><th>Planted</th><th>Flagged</th><th>True positives</th><th>False positives</th><th>False negatives</th><th>Precision</th><th>Recall</th><th>F1</th></tr>
<tr><td>Nominee director network</td><td>6,157</td><td>5,988</td><td>5,987</td><td>1</td><td>170</td><td>1.000</td><td>0.972</td><td>0.986</td></tr>
<tr><td>Mass registration address</td><td>12,195</td><td>12,195</td><td>12,195</td><td>0</td><td>0</td><td>1.000</td><td>1.000</td><td>1.000</td></tr>
<tr><td>Circular ownership</td><td>1,296</td><td>1,280</td><td>1,280</td><td>0</td><td>16</td><td>1.000</td><td>0.988</td><td>0.994</td></tr>
<tr><td>Sanctions proximity</td><td>309</td><td>454</td><td>298</td><td>156</td><td>11</td><td>0.656</td><td>0.964</td><td>0.781</td></tr>
<tr><td>Opaque offshore ownership</td><td>7,407</td><td>7,357</td><td>7,357</td><td>0</td><td>50</td><td>1.000</td><td>0.993</td><td>0.997</td></tr>
<tr><td>Burst incorporation and phoenix activity</td><td>2,467</td><td>2,461</td><td>2,461</td><td>0</td><td>6</td><td>1.000</td><td>0.998</td><td>0.999</td></tr>
</table>

## Systems compared on the label any planted typology

<table>
<tr><th>System</th><th>Average precision</th><th>ROC AUC</th><th>Precision at 100</th><th>Precision at 1,000</th><th>Recall at 1 percent budget</th><th>Recall at 5 percent budget</th><th>Recall at 10 percent budget</th></tr>
<tr><td>Veil Pierce rule fusion</td><td>0.986</td><td>0.998</td><td>0.80</td><td>0.980</td><td>0.126</td><td>0.628</td><td>0.997</td></tr>
<tr><td>Gradient boosted challenger</td><td>0.999</td><td>1.000</td><td>1.00</td><td>1.000</td><td>0.127</td><td>0.636</td><td>1.000</td></tr>
<tr><td>Direct name screening only</td><td>0.082</td><td>0.502</td><td>0.80</td><td>0.141</td><td>0.013</td><td>0.053</td><td>0.104</td></tr>
<tr><td>Address density rule</td><td>0.308</td><td>0.832</td><td>0.02</td><td>0.018</td><td>0.002</td><td>0.268</td><td>0.506</td></tr>
<tr><td>Appointment count rule</td><td>0.395</td><td>0.674</td><td>1.00</td><td>1.000</td><td>0.127</td><td>0.304</td><td>0.386</td></tr>
</table>

At the alert threshold of 0.50 the rule fusion raises 19,621 alerts with precision 0.992 and recall 0.990.

<table>
<tr><th>Risk band</th><th>Companies</th><th>Share that is truly planted</th></tr>
<tr><td>Critical</td><td>8,759</td><td>0.993</td></tr>
<tr><td>High</td><td>8,222</td><td>0.990</td></tr>
<tr><td>Medium</td><td>3,078</td><td>0.891</td></tr>
<tr><td>Low</td><td>229,941</td><td>0.000</td></tr>
</table>

<table>
<tr><th>Population</th><th>Companies</th><th>Alert rate</th><th>Mean risk score</th></tr>
<tr><td>benign agent</td><td>14,608</td><td>0.0008</td><td>0.258</td></tr>
<tr><td>foreign parent</td><td>1,375</td><td>0.0007</td><td>0.094</td></tr>
<tr><td>group tree</td><td>11,735</td><td>0.0019</td><td>0.042</td></tr>
<tr><td>namesake</td><td>334</td><td>0.0808</td><td>0.085</td></tr>
<tr><td>professional director</td><td>5,627</td><td>0.0004</td><td>0.267</td></tr>
<tr><td>spv batch</td><td>1,060</td><td>0.0000</td><td>0.193</td></tr>
<tr><td>ordinary background</td><td>195,601</td><td>0.0005</td><td>0.016</td></tr>
</table>

## Ablations

<table>
<tr><th>Typology</th><th>Capability removed</th><th>Precision full</th><th>Recall full</th><th>Precision without</th><th>Recall without</th></tr>
<tr><td>nominee</td><td>person entity resolution</td><td>1.000</td><td>0.972</td><td>1.000</td><td>0.763</td></tr>
<tr><td>address factory</td><td>address resolution</td><td>1.000</td><td>1.000</td><td>1.000</td><td>0.121</td></tr>
<tr><td>circular</td><td>leak data edges</td><td>1.000</td><td>0.988</td><td>1.000</td><td>0.621</td></tr>
<tr><td>sanctions</td><td>transliteration and birth date logic</td><td>0.656</td><td>0.964</td><td>0.168</td><td>0.738</td></tr>
<tr><td>sanctions direct only</td><td>multi hop control traversal</td><td>0.656</td><td>0.964</td><td>0.398</td><td>0.311</td></tr>
<tr><td>opaque</td><td>jurisdiction opacity weights and filing health</td><td>1.000</td><td>0.993</td><td>0.688</td><td>1.000</td></tr>
<tr><td>phoenix burst</td><td>abandonment test on batches</td><td>1.000</td><td>0.998</td><td>0.699</td><td>0.998</td></tr>
</table>

## Retrieval

<table>
<tr><th>Typology retrieval</th><th>MRR</th><th>Hit at 1</th><th>Hit at 3</th></tr>
<tr><td>bm25</td><td>0.922</td><td>0.875</td><td>0.958</td></tr>
<tr><td>dense</td><td>0.904</td><td>0.833</td><td>0.979</td></tr>
<tr><td>hybrid</td><td>0.925</td><td>0.875</td><td>0.979</td></tr>
</table>

48 analyst questions over 25 cards.

<table>
<tr><th>Name lookup channel</th><th>Hit at 1</th><th>Hit at 5</th></tr>
<tr><td>exact</td><td>0.231</td><td>0.231</td></tr>
<tr><td>word</td><td>0.485</td><td>0.623</td></tr>
<tr><td>rrf</td><td>0.688</td><td>0.887</td></tr>
<tr><td>blend</td><td>0.903</td><td>0.957</td></tr>
<tr><td>char</td><td>0.912</td><td>0.960</td></tr>
</table>

1,000 noisy queries against an index of 525,195 names.

## Narrative verification

<table>
<tr><th>Measure</th><th>Value</th></tr>
<tr><td>Narrator</td><td>offline (grounded composer)</td></tr>
<tr><td>Dossiers written</td><td>1,782</td></tr>
<tr><td>Claims checked</td><td>15,616</td></tr>
<tr><td>Claims supported by cited evidence</td><td>15,616</td></tr>
<tr><td>Mean evidence items per dossier</td><td>6.6</td></tr>
<tr><td>Fabricated claims tested</td><td>12,422</td></tr>
<tr><td>Fabricated claims rejected</td><td>12,400</td></tr>
<tr><td>Hostile names planted and detected</td><td>50 of 50</td></tr>
<tr><td>False alarms on ordinary names</td><td>0 of 249,950</td></tr>
<tr><td>Prompts or narratives that contained the hostile text</td><td>0 of 50</td></tr>
</table>

<table>
<tr><th>Kind of fabricated claim</th><th>Tested</th><th>Rejected</th><th>Rate</th></tr>
<tr><td>altered number</td><td>1,730</td><td>1,708</td><td>0.987</td></tr>
<tr><td>citation removed</td><td>1,782</td><td>1,782</td><td>1.000</td></tr>
<tr><td>citation to a missing item</td><td>1,782</td><td>1,782</td><td>1.000</td></tr>
<tr><td>entity from another case</td><td>1,782</td><td>1,782</td><td>1.000</td></tr>
<tr><td>contradicted risk band</td><td>1,782</td><td>1,782</td><td>1.000</td></tr>
<tr><td>assertion of guilt</td><td>1,782</td><td>1,782</td><td>1.000</td></tr>
<tr><td>echoed registry instruction</td><td>1,782</td><td>1,782</td><td>1.000</td></tr>
</table>

## Supervised challenger

Out of fold average precision 0.9991, ROC AUC 0.9999, Brier score 0.0043 over 5 grouped folds and 34 raw features.

<table>
<tr><th>Share of positives labelled</th><th>Labelled cases</th><th>Average precision</th></tr>
<tr><td>1 percent</td><td>180</td><td>0.983</td></tr>
<tr><td>3 percent</td><td>603</td><td>0.994</td></tr>
<tr><td>10 percent</td><td>1,971</td><td>0.997</td></tr>
<tr><td>30 percent</td><td>5,909</td><td>0.991</td></tr>
<tr><td>100 percent</td><td>19,660</td><td>0.999</td></tr>
</table>

<table>
<tr><th>Feature</th><th>Permutation importance</th></tr>
<tr><td>addr_director_diversity</td><td>0.2727</td></tr>
<tr><td>addr_shell_ratio</td><td>0.1653</td></tr>
<tr><td>upstream_opacity</td><td>0.0367</td></tr>
<tr><td>chain_depth</td><td>0.0053</td></tr>
<tr><td>phoenix_link</td><td>0.0020</td></tr>
<tr><td>no_person_in_chain</td><td>0.0016</td></tr>
<tr><td>max_director_companies</td><td>0.0006</td></tr>
<tr><td>sanction_proximity</td><td>0.0006</td></tr>
</table>

## Runtime

<table>
<tr><th>Stage</th><th>Seconds</th></tr>
<tr><td>load registry</td><td>0.6</td></tr>
<tr><td>entity resolution and graph build</td><td>61.1</td></tr>
<tr><td>detection</td><td>5.5</td></tr>
<tr><td>challenger model</td><td>41.5</td></tr>
<tr><td>name index</td><td>28.6</td></tr>
<tr><td>evaluation</td><td>106.9</td></tr>
<tr><td>label budget study</td><td>48.4</td></tr>
<tr><td>figures</td><td>5.0</td></tr>
<tr><td>sample dossiers</td><td>0.7</td></tr>
<tr><td>total</td><td>298.3</td></tr>
</table>

Peak memory 3.24 GB.
