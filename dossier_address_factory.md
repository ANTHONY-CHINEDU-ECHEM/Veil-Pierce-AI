# Due diligence dossier: KENDAL TRAINING HOUSE LIMITED

<table>
<tr><th>Company number</th><th>Risk score</th><th>Risk band</th><th>Typologies triggered</th><th>Narrative source</th></tr>
<tr><td>11596945</td><td>0.97</td><td>Critical</td><td>2</td><td>offline (grounded composer)</td></tr>
</table>

This dossier describes indicators of risk found in public and leaked records. It does not establish that any person or company has committed an offence. Every finding needs confirmation by a trained reviewer before action is taken.

## Summary

* KENDAL TRAINING HOUSE LIMITED (company 11596945) has a fused risk score of 0.97, which places it in the Critical band. [M01]
* 2 of the six concealment typologies are triggered: Nominee director network, Mass registration address. [M01]
* The company was incorporated on 02 Feb 2023 and was dissolved on 04 Jan 2024. Its status is Dissolved and its accounts category is NO ACCOUNTS FILED. [E02]

## Typology scores

<table>
<tr><th>Typology</th><th>Score</th><th>Triggered</th></tr>
<tr><td>Nominee director network</td><td>0.94</td><td>yes</td></tr>
<tr><td>Mass registration address</td><td>0.92</td><td>yes</td></tr>
<tr><td>Circular ownership</td><td>0.00</td><td>no</td></tr>
<tr><td>Sanctions proximity</td><td>0.00</td><td>no</td></tr>
<tr><td>Opaque offshore ownership</td><td>0.00</td><td>no</td></tr>
<tr><td>Burst incorporation and phoenix activity</td><td>0.00</td><td>no</td></tr>
</table>

## Findings

* Nominee director network (score 0.94). The director Fiona Clarke Pemberton holds 173 director appointments, 94 percent of them in shell like companies, and is the sole director of 92 percent. [E03][E05][M01]
* Guidance on this pattern: Volume on its own is not proof. Accountants and professional directors also hold many appointments. The combination of volume with disposable companies and sole directorships is what marks a nominee network. [T01]
* Mass registration address (score 0.92). The registered office is shared by 899 companies, 96 percent of which are shell like, with 78 percent of directors resident overseas. [E02][E06][M01]
* Guidance on this pattern: A registered office gives a shell an appearance of UK substance. A shared address with a high share of disposable companies is one of the strongest network level indicators available from public data. [T04]

## Ownership and control

* No person with significant control is recorded for company 11596945. [E04]
* Fiona Clarke Pemberton (person 767, born Dec 1952), usual residence Panama, is recorded as director of KENDAL TRAINING HOUSE LIMITED (company 11596945), appointed 02 Feb 2023. [E03]

## Recommended controls

<table>
<tr><th>Typology</th><th>Preventive control</th><th>Corrective action</th><th>Owner</th><th>Regulatory anchor</th></tr>
<tr><td>Nominee director network</td><td>Onboarding rule: enhanced due diligence for any company whose director exceeds the appointment threshold.</td><td>Review every company fronted by the confirmed nominee as one connected case and exit or restrict where control cannot be evidenced.</td><td>Financial crime operations</td><td>MLR 2017 regulations 28 and 33</td></tr>
<tr><td>Mass registration address</td><td>Address risk rating applied at onboarding to every company registered at a flagged address.</td><td>Bulk review of existing customers at the address and report of suspected false addresses to the registrar.</td><td>Customer due diligence team</td><td>Economic Crime and Corporate Transparency Act 2023 registered office rules</td></tr>
</table>

Reviewer steps for Nominee director network [T01]:

* Request evidence of who gives instructions to the director
* Treat every company fronted by the same nominee as one connected risk
* Apply enhanced due diligence before onboarding or continuing the relationship

Reviewer steps for Mass registration address [T04]:

* Treat the address as a risk factor for every company registered there
* Check whether the business has any real presence at the address
* Report suspected false addresses to the registrar

## Evidence register

<table>
<tr><th>Item</th><th>Kind</th><th>Statement</th><th>Source</th></tr>
<tr><td>M01</td><td>model</td><td>Deterministic detectors give KENDAL TRAINING HOUSE LIMITED (company 11596945) a fused risk score of 0.97, band Critical. Typology scores: Nominee director network 0.94; Mass registration address 0.92; Circular ownership 0.00; Sanctions proximity 0.00; Opaque offshore ownership 0.00; Burst incorporation and phoenix activity 0.00. Typologies triggered (2): Nominee director network, Mass registration address.</td><td>Veil Pierce AI detectors</td></tr>
<tr><td>E02</td><td>profile</td><td>KENDAL TRAINING HOUSE LIMITED (company 11596945) was incorporated on 02 Feb 2023, status Dissolved, dissolved 04 Jan 2024. Accounts category: NO ACCOUNTS FILED. Registered office: 5th Floor, 107 Chapel Square, Reading RG1 9PF. Activity code: 96090 Other service activities not elsewhere classified.</td><td>company register</td></tr>
<tr><td>E03</td><td>officer</td><td>Fiona Clarke Pemberton (person 767, born Dec 1952), usual residence Panama, is recorded as director of KENDAL TRAINING HOUSE LIMITED (company 11596945), appointed 02 Feb 2023.</td><td>officer register, appointment 6826</td></tr>
<tr><td>E04</td><td>control</td><td>No person with significant control is recorded for company 11596945.</td><td>control register</td></tr>
<tr><td>E05</td><td>analysis</td><td>Entity resolution links 20 name spellings to Fiona Clarke Pemberton (person 767, born Dec 1952) (for example Fiona Clarke Pemberton, Fiona Pemberton, Fiona C Pemberton, Fina Clarke Pemberton, Fioa Clarke Pemberton). That person holds 173 director appointments. 94 percent of those companies are shell like (dissolved within two years, dormant, or overdue with no accounts) and the person is the sole director of 92 percent.</td><td>entity resolution and appointment analysis</td></tr>
<tr><td>E06</td><td>analysis</td><td>899 companies share the resolved address 5th Floor, 107 Chapel Square, Reading RG1 9PF. 96 percent of them are shell like, 78 percent of their directors are resident overseas, and the busiest 14 day window accounts for 7 percent of all incorporations there.</td><td>address resolution and address statistics</td></tr>
</table>

## Typology cards retrieved

<table>
<tr><th>Card</th><th>Title</th><th>Reading references</th></tr>
<tr><td>T01</td><td>Professional nominee directors fronting many companies</td><td>FATF and Egmont Group, Concealment of Beneficial Ownership (2018); HM Treasury and Home Office, National Risk Assessment of Money Laundering and Terrorist Financing (2020)</td></tr>
<tr><td>T04</td><td>Mass registration addresses and company factories</td><td>HM Treasury and Home Office, National Risk Assessment of Money Laundering and Terrorist Financing (2020); FATF and Egmont Group, Concealment of Beneficial Ownership (2018)</td></tr>
<tr><td>T06</td><td>Registered office abuse and inappropriate addresses</td><td>Economic Crime and Corporate Transparency Act 2023</td></tr>
<tr><td>T24</td><td>Limits of automated findings</td><td>Joint Money Laundering Steering Group, Guidance for the UK Financial Sector; FATF, Guidance on Beneficial Ownership of Legal Persons (2023)</td></tr>
</table>

## Verification and audit

<table>
<tr><th>Claims checked</th><th>Claims supported</th><th>Fallback used</th><th>Configuration fingerprint</th><th>Data snapshot</th></tr>
<tr><td>9</td><td>9</td><td>no</td><td>3681c04b7099</td><td>2026/09/30</td></tr>
</table>
