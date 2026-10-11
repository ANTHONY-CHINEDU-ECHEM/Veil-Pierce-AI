# Due diligence dossier: LUDLOW TAXIS INTERNATIONAL LIMITED

<table>
<tr><th>Company number</th><th>Risk score</th><th>Risk band</th><th>Typologies triggered</th><th>Narrative source</th></tr>
<tr><td>12374602</td><td>0.96</td><td>Critical</td><td>2</td><td>offline (grounded composer)</td></tr>
</table>

This dossier describes indicators of risk found in public and leaked records. It does not establish that any person or company has committed an offence. Every finding needs confirmation by a trained reviewer before action is taken.

## Summary

* LUDLOW TAXIS INTERNATIONAL LIMITED (company 12374602) has a fused risk score of 0.96, which places it in the Critical band. [M01]
* 2 of the six concealment typologies are triggered: Circular ownership, Opaque offshore ownership. [M01]
* The company was incorporated on 20 Apr 2021. Its status is Liquidation and its accounts category is MICRO ENTITY. [E02]

## Typology scores

<table>
<tr><th>Typology</th><th>Score</th><th>Triggered</th></tr>
<tr><td>Nominee director network</td><td>0.00</td><td>no</td></tr>
<tr><td>Mass registration address</td><td>0.00</td><td>no</td></tr>
<tr><td>Circular ownership</td><td>0.95</td><td>yes</td></tr>
<tr><td>Sanctions proximity</td><td>0.00</td><td>no</td></tr>
<tr><td>Opaque offshore ownership</td><td>0.65</td><td>yes</td></tr>
<tr><td>Burst incorporation and phoenix activity</td><td>0.00</td><td>no</td></tr>
</table>

## Findings

* Circular ownership (score 0.95). The company sits on a closed loop of declared control with 5 links: LUDLOW TAXIS INTERNATIONAL LIMITED, which controls PENNINE WIRELESS DEVELOPMENTS LIMITED, which controls ATLAS ROBOTICS COLLECTIVE LIMITED, which controls WESTBROOK LANTERN CYCLES INC, which controls VIOLET WASTE EXPRESS LIMITED, which controls LUDLOW TAXIS INTERNATIONAL LIMITED. No natural person appears on the loop. [E09][E08][E07][E06][E05][E10][M01]
* Guidance on this pattern: A loop of declared control cannot be a true statement of ultimate ownership. It either conceals the real owner or reflects false filings, and both justify escalation. [T07]
* Opaque offshore ownership (score 0.65). The declared chain of control reaches no natural person. It ends at WESTBROOK LANTERN CYCLES INC, registered in Mauritius. [E06][E07][E11][M01]
* Guidance on this pattern: Recording an offshore company as the controller ends the public trail at the border. It is one of the most common ways the control register is defeated. [T14]

## Ownership and control

* VIOLET WASTE EXPRESS LIMITED (company 07740361) is recorded as a corporate controller of LUDLOW TAXIS INTERNATIONAL LIMITED (company 12374602): ownership of shares 75 to 100 percent; filed as VIOLET WASTE EXPRESS LIMITED; resolved by registration number, notified 20 Apr 2021. Link confidence 1.00. [E05]
* WESTBROOK LANTERN CYCLES INC (offshore entity 81001683, Mauritius) is recorded as a corporate controller of VIOLET WASTE EXPRESS LIMITED (company 07740361): ownership of shares 75 to 100 percent; filed as WESTBROOK LANTERN CYCLES INC; resolved by name and jurisdiction, notified 17 Aug 2020. Link confidence 1.00. [E06]
* Leak data records ATLAS ROBOTICS COLLECTIVE LIMITED (company 15531012) as shareholder of WESTBROOK LANTERN CYCLES INC (offshore entity 81001683, Mauritius). The leak officer was matched to the UK company by name. [E07]
* PENNINE WIRELESS DEVELOPMENTS LIMITED (company 10697355) is recorded as a corporate controller of ATLAS ROBOTICS COLLECTIVE LIMITED (company 15531012): ownership of shares 75 to 100 percent; filed as PENNINE WIRELESS DEVELOPMENTS LIMITED; resolved by registration number, notified 06 Apr 2016. Link confidence 1.00. [E08]
* LUDLOW TAXIS INTERNATIONAL LIMITED (company 12374602) is recorded as a corporate controller of PENNINE WIRELESS DEVELOPMENTS LIMITED (company 10697355): ownership of shares 75 to 100 percent; filed as LUDLOW TAXIS INTERNATIONAL LIMITED; resolved by registration number, notified 10 Sep 2026. Link confidence 1.00. [E09]
* Fang Kang Li (person 4466, born Nov 1973), usual residence England, is recorded as director of LUDLOW TAXIS INTERNATIONAL LIMITED (company 12374602), appointed 18 Mar 2023. [E03]
* Nia Ncube (person 4467, born Dec 1968), usual residence England, is recorded as director of LUDLOW TAXIS INTERNATIONAL LIMITED (company 12374602), appointed 20 Apr 2021. [E04]

## Recommended controls

<table>
<tr><th>Typology</th><th>Preventive control</th><th>Corrective action</th><th>Owner</th><th>Regulatory anchor</th></tr>
<tr><td>Circular ownership</td><td>Onboarding block until a natural person is evidenced as ultimate owner.</td><td>Discrepancy report to the registrar and escalation to the nominated officer.</td><td>Customer due diligence team</td><td>Companies Act 2006 Part 21A and MLR 2017 regulation 30A</td></tr>
<tr><td>Opaque offshore ownership</td><td>Requirement for certified ownership documents before onboarding any company with an offshore corporate controller.</td><td>Enhanced due diligence, discrepancy report and exit where the owner cannot be identified.</td><td>Customer due diligence team</td><td>Companies Act 2006 Part 21A and MLR 2017 regulation 28</td></tr>
</table>

Reviewer steps for Circular ownership [T07]:

* Refuse to accept the structure as evidence of beneficial ownership
* Require the customer to name the natural persons who ultimately benefit
* Report the discrepancy to the registrar

Reviewer steps for Opaque offshore ownership [T14]:

* Require identification of the natural persons behind the offshore entity
* Obtain certified ownership documents from the offshore registered agent
* Report the discrepancy between the register and the information obtained

## Evidence register

<table>
<tr><th>Item</th><th>Kind</th><th>Statement</th><th>Source</th></tr>
<tr><td>M01</td><td>model</td><td>Deterministic detectors give LUDLOW TAXIS INTERNATIONAL LIMITED (company 12374602) a fused risk score of 0.96, band Critical. Typology scores: Nominee director network 0.00; Mass registration address 0.00; Circular ownership 0.95; Sanctions proximity 0.00; Opaque offshore ownership 0.65; Burst incorporation and phoenix activity 0.00. Typologies triggered (2): Circular ownership, Opaque offshore ownership.</td><td>Veil Pierce AI detectors</td></tr>
<tr><td>E02</td><td>profile</td><td>LUDLOW TAXIS INTERNATIONAL LIMITED (company 12374602) was incorporated on 20 Apr 2021, status Liquidation. Accounts category: MICRO ENTITY. Registered office: 226 King Square, Leeds LS1 9HQ. Activity code: 86900 Other human health activities.</td><td>company register</td></tr>
<tr><td>E03</td><td>officer</td><td>Fang Kang Li (person 4466, born Nov 1973), usual residence England, is recorded as director of LUDLOW TAXIS INTERNATIONAL LIMITED (company 12374602), appointed 18 Mar 2023.</td><td>officer register, appointment 15874</td></tr>
<tr><td>E04</td><td>officer</td><td>Nia Ncube (person 4467, born Dec 1968), usual residence England, is recorded as director of LUDLOW TAXIS INTERNATIONAL LIMITED (company 12374602), appointed 20 Apr 2021.</td><td>officer register, appointment 15877</td></tr>
<tr><td>E05</td><td>control</td><td>VIOLET WASTE EXPRESS LIMITED (company 07740361) is recorded as a corporate controller of LUDLOW TAXIS INTERNATIONAL LIMITED (company 12374602): ownership of shares 75 to 100 percent; filed as VIOLET WASTE EXPRESS LIMITED; resolved by registration number, notified 20 Apr 2021. Link confidence 1.00.</td><td>control register, control record 13940</td></tr>
<tr><td>E06</td><td>ownership chain</td><td>WESTBROOK LANTERN CYCLES INC (offshore entity 81001683, Mauritius) is recorded as a corporate controller of VIOLET WASTE EXPRESS LIMITED (company 07740361): ownership of shares 75 to 100 percent; filed as WESTBROOK LANTERN CYCLES INC; resolved by name and jurisdiction, notified 17 Aug 2020. Link confidence 1.00.</td><td>control register, control record 13941</td></tr>
<tr><td>E07</td><td>ownership chain</td><td>Leak data records ATLAS ROBOTICS COLLECTIVE LIMITED (company 15531012) as shareholder of WESTBROOK LANTERN CYCLES INC (offshore entity 81001683, Mauritius). The leak officer was matched to the UK company by name.</td><td>offshore leak data</td></tr>
<tr><td>E08</td><td>ownership chain</td><td>PENNINE WIRELESS DEVELOPMENTS LIMITED (company 10697355) is recorded as a corporate controller of ATLAS ROBOTICS COLLECTIVE LIMITED (company 15531012): ownership of shares 75 to 100 percent; filed as PENNINE WIRELESS DEVELOPMENTS LIMITED; resolved by registration number, notified 06 Apr 2016. Link confidence 1.00.</td><td>control register, control record 13942</td></tr>
<tr><td>E09</td><td>ownership chain</td><td>LUDLOW TAXIS INTERNATIONAL LIMITED (company 12374602) is recorded as a corporate controller of PENNINE WIRELESS DEVELOPMENTS LIMITED (company 10697355): ownership of shares 75 to 100 percent; filed as LUDLOW TAXIS INTERNATIONAL LIMITED; resolved by registration number, notified 10 Sep 2026. Link confidence 1.00.</td><td>control register, control record 13939</td></tr>
<tr><td>E10</td><td>analysis</td><td>The shortest loop of declared control through company 12374602 has 5 links. No natural person appears on it.</td><td>strongly connected component analysis</td></tr>
<tr><td>E11</td><td>analysis</td><td>Walking up the control records from company 12374602 finds no natural person within 8 steps. The longest chain of corporate owners above it has 8 link(s) and the highest jurisdiction opacity weight on the chain is 0.60.</td><td>ownership chain analysis</td></tr>
</table>

## Typology cards retrieved

<table>
<tr><th>Card</th><th>Title</th><th>Reading references</th></tr>
<tr><td>T07</td><td>Circular ownership structures</td><td>FATF and Egmont Group, Concealment of Beneficial Ownership (2018); Companies Act 2006, Part 21A (persons with significant control)</td></tr>
<tr><td>T14</td><td>Corporate controllers registered in secrecy jurisdictions</td><td>Companies Act 2006, Part 21A (persons with significant control); FATF and Egmont Group, Concealment of Beneficial Ownership (2018); FATF, Guidance on Beneficial Ownership of Legal Persons (2023)</td></tr>
<tr><td>T16</td><td>Hidden controllers revealed by leak data</td><td>ICIJ, Offshore Leaks Database notes on use of the data; FATF and Egmont Group, Concealment of Beneficial Ownership (2018)</td></tr>
<tr><td>T24</td><td>Limits of automated findings</td><td>Joint Money Laundering Steering Group, Guidance for the UK Financial Sector; FATF, Guidance on Beneficial Ownership of Legal Persons (2023)</td></tr>
</table>

## Verification and audit

<table>
<tr><th>Claims checked</th><th>Claims supported</th><th>Fallback used</th><th>Configuration fingerprint</th><th>Data snapshot</th></tr>
<tr><td>14</td><td>14</td><td>no</td><td>3681c04b7099</td><td>2026/09/30</td></tr>
</table>
