# Data dictionary

## Canonical tables

Every stage after loading works on these seven tables, whether the data is synthetic or real.

### companies

<table>
<tr><th>Column</th><th>Meaning</th></tr>
<tr><td>company_number</td><td>Eight character registration number, the key of the table</td></tr>
<tr><td>company_name</td><td>Registered name as filed</td></tr>
<tr><td>status</td><td>Active, Dissolved or Liquidation</td></tr>
<tr><td>category</td><td>Legal form, for example Private Limited Company</td></tr>
<tr><td>incorporation_date, dissolution_date</td><td>Dates. Dissolution is empty for live companies</td></tr>
<tr><td>address_line1, post_town, postcode, country</td><td>Registered office as filed</td></tr>
<tr><td>sic_code, sic_text</td><td>Activity code and its description</td></tr>
<tr><td>accounts_category</td><td>Type of the last accounts, or NO ACCOUNTS FILED</td></tr>
<tr><td>accounts_overdue</td><td>True when accounts are past their due date</td></tr>
</table>

### officers

<table>
<tr><th>Column</th><th>Meaning</th></tr>
<tr><td>appointment_id</td><td>Key of the table</td></tr>
<tr><td>company_number</td><td>Company the appointment belongs to</td></tr>
<tr><td>officer_name</td><td>Name as filed, surname first</td></tr>
<tr><td>officer_kind</td><td>person or corporate</td></tr>
<tr><td>role</td><td>director or secretary</td></tr>
<tr><td>dob_year, dob_month</td><td>Year and month of birth. Zero when absent</td></tr>
<tr><td>nationality, country_of_residence, occupation</td><td>As filed</td></tr>
<tr><td>appointed_on, resigned_on</td><td>Dates</td></tr>
</table>

### pscs (persons with significant control)

<table>
<tr><th>Column</th><th>Meaning</th></tr>
<tr><td>psc_id</td><td>Key of the table</td></tr>
<tr><td>company_number</td><td>Company that is controlled</td></tr>
<tr><td>kind</td><td>individual, corporate or statement (a statement that no registrable person exists)</td></tr>
<tr><td>name</td><td>Name of the controller as filed</td></tr>
<tr><td>dob_year, dob_month, nationality, country_of_residence</td><td>For individuals</td></tr>
<tr><td>natures_of_control</td><td>Text of the nature of control, separated by a vertical bar when there are several</td></tr>
<tr><td>ownership_band</td><td>Midpoint of the strongest ownership or voting band, between 0 and 1</td></tr>
<tr><td>notified_on</td><td>Date</td></tr>
<tr><td>registration_number, country_registered, legal_form</td><td>For corporate controllers, as filed</td></tr>
</table>

### offshore_entities, offshore_officers, offshore_edges

<table>
<tr><th>Table</th><th>Columns</th></tr>
<tr><td>offshore_entities</td><td>node_id, name, jurisdiction, incorporation_date, status, source</td></tr>
<tr><td>offshore_officers</td><td>node_id, name, kind (person or company), country</td></tr>
<tr><td>offshore_edges</td><td>start_id, end_id, link (for example shareholder of, director of, beneficiary of). The start is an officer or an entity and the end is always an entity</td></tr>
</table>

### sanctions

<table>
<tr><th>Column</th><th>Meaning</th></tr>
<tr><td>entity_id</td><td>Key of the list entry</td></tr>
<tr><td>schema</td><td>Person or Company</td></tr>
<tr><td>name, aliases</td><td>Primary name and other names separated by semicolons</td></tr>
<tr><td>birth_year, birth_month</td><td>Zero when the list does not give them</td></tr>
<tr><td>regime</td><td>Sanctions regime or programme</td></tr>
<tr><td>listed_on</td><td>Date</td></tr>
</table>

## Public sources and how they map

<table>
<tr><th>Source</th><th>File the loader looks for</th><th>Loader</th><th>Notes</th></tr>
<tr><td>Companies House free company data product</td><td>BasicCompanyData*.csv</td><td>load_companies_house_csv</td><td>Column names are trimmed of stray spaces. Dates are day, month, year. The activity field is split into code and text. This product lists live companies only, so lifespan features need archived snapshots or the API to see dissolved companies.</td></tr>
<tr><td>Companies House persons with significant control snapshot</td><td>psc*snapshot*</td><td>load_psc_snapshot</td><td>One JSON record per line. Ceased records are dropped. The kind and nature values are normalised to plain words.</td></tr>
<tr><td>Officer appointments</td><td>officers*.csv</td><td>load_officers_csv</td><td>No free bulk file exists. The loader reads a CSV with the columns of the officers table above and dates written as year, month, day separated by slashes. It can be filled from the Companies House API or a licensed bulk product.</td></tr>
<tr><td>OpenSanctions simplified targets (which include the OFSI and OFAC lists)</td><td>targets*.csv</td><td>load_opensanctions_simple</td><td>Persons, companies, organisations and legal entities are kept. The first birth date is used.</td></tr>
<tr><td>ICIJ Offshore Leaks database</td><td>nodes*entities*.csv, nodes*officers*.csv, relationships*.csv</td><td>load_icij</td><td>Officer nodes are classed as companies when their name carries a legal form word. Only officer and intermediary relationships are kept.</td></tr>
</table>

Place the files in one folder and run `veilpierce build source=FOLDER snapshot=2026/09/30`.

The loaders were verified by writing a synthetic registry in these layouts and reading it back (see `tests/test_loaders.py`). They were written from the published descriptions of each source and have not been run against the multi gigabyte originals, which could not be downloaded in the environment where this project was built. Expect to adjust a column name or two on first contact with a live file.

## Ground truth tables (synthetic data only)

<table>
<tr><th>Table</th><th>Content</th></tr>
<tr><td>company_labels</td><td>One row per company: a flag per typology, the flag suspicious, the true hop distance to a listed party, the planted group, the kind of benign lookalike, and whether the name was replaced by a hostile instruction</td></tr>
<tr><td>officers, pscs</td><td>The true person behind every record, and the true target of every corporate controller</td></tr>
<tr><td>sanctions, sanction_reach</td><td>Which list entries are linked to the registry, through what, and which companies they reach at how many steps</td></tr>
<tr><td>addresses, persons</td><td>The planted factory and agent addresses, and the planted nominees and professional directors</td></tr>
<tr><td>leak_company_links</td><td>Which leak data officers are UK companies</td></tr>
</table>
