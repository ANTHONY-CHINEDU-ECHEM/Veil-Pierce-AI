# Architecture

![Architecture](figures/architecture.png)

Veil Pierce AI is a pipeline of six stages. Each stage is a package under `veilpierce/` with one responsibility, and each stage hands the next a plain data structure that can be inspected, saved and tested on its own.

## Stage one: data

Package `veilpierce/data`.

Seven canonical tables describe the world: companies, officer appointments, control records, offshore entities, offshore officers, offshore relationships and sanctions entries. Two things can fill them.

* `synth.py` generates a registry of any size with six concealment typologies planted inside realistic background noise, and records the ground truth of everything it planted. The truth tables are held apart from the working tables and a test confirms that no truth column leaks into them.
* `loaders.py` reads the layouts of the public sources into the same canonical tables, and can write a synthetic registry back out in those layouts so that the loaders are exercised by a round trip test.

`store.py` persists the tables as parquet.

## Stage two: entity resolution

Package `veilpierce/resolution`.

Raw filings name people, companies and addresses as free text. Four resolvers turn that text into identities.

* `persons.py` clusters officer and control records into natural persons. Records are blocked on month and year of birth together with a transliteration key of the surname, and again on the forename key, so that a typing slip in either name still leaves one block where the two records meet. Inside a block, names are compared with Jaro Winkler similarity and rules for initials and middle names. Linked pairs are merged with a connected components pass.
* `corporates.py` ties each corporate controller to a UK company (by registration number, exact name, name without legal form, or fuzzy name), to an offshore entity from the leak data (by name and canonical jurisdiction), or to a foreign company stub. It also ties UK companies that appear as shareholders in the leak data back to the register.
* Address resolution (in `textnorm.py`) reduces every registered office to a key built from postcode, building number and street, ignoring suites, floors and abbreviations.
* `sanctions.py` screens every person and entity against the list. Candidates are generated from a shared token index over transliteration keys, then scored on name similarity with token alignment, and finally adjusted by date of birth evidence.

## Stage three: knowledge graph

Package `veilpierce/graph`.

`build.py` assembles the resolved identities into one typed property graph. Node kinds are company, person, address, offshore entity, foreign company, leak data officer and sanctions list entry. Edge types are officer of, controls, registered at, leak officer of, leak shareholder of and sanctions match. Control edges always point from the controller to the controlled entity, which is what makes directed traversal meaningful.

`store.py` keeps the graph as flat numpy arrays with compressed row indexes. `algorithms.py` implements strongly connected components for loops, a vectorised breadth first search that follows the direction of control, an iterative ownership profile, and single entity path extraction.

## Stage four: detectors

Package `veilpierce/detect`.

Six detectors each produce a score between 0 and 1 for every company. `engine.py` runs them, applies the flag thresholds and fuses the scores with a noisy OR, so that independent typologies reinforce each other. `risk_model.py` trains a gradient boosted challenger on the raw features when confirmed labels are available. The formulas are set out in [methodology.md](methodology.md).

## Stage five: graph RAG

Package `veilpierce/rag`.

* `graph_retriever.py` walks the neighbourhood of a company and turns each edge and each analysis result into a numbered evidence item written in plain language, with its source.
* `typology.py` and `index.py` hold the typology library and retrieve the cards that match each finding with BM25 and a dense channel fused by reciprocal rank.
* `guard.py` withholds registry text that reads like an instruction before any prompt is built.
* `llm.py` provides the narrators. The offline composer is the default. Providers for hosted and local language models share the same interface.
* `verifier.py` checks every claim of every narrative against the cited evidence and removes what is not supported.
* `investigator.py` runs the loop and adds the recommended controls from the mitigation matrix. `report.py` renders the dossier.

## Stage six: delivery

`pipeline.py` orchestrates a run and saves artefacts. `cli.py` exposes every operation as a command. `api/app.py` serves risk scores, dossiers, graphs, name search and questions over HTTP from the saved artefacts. `evaluation/` scores every stage against ground truth and draws the figures.

## Design decisions

<table>
<tr><th>Decision</th><th>Reason</th></tr>
<tr><td>Scores come from deterministic detectors, never from the language model</td><td>A risk decision must be repeatable and explainable to an auditor, and a model that has been manipulated must not be able to clear a company.</td></tr>
<tr><td>Rule fusion is the headline score and the supervised model is a challenger</td><td>A real registry has no labels. The system has to work on the first day, before any confirmed cases exist.</td></tr>
<tr><td>The offline composer is the default narrator</td><td>Every benchmark run is reproducible with no network, no key and no cost, and the same verifier guards both narrators.</td></tr>
<tr><td>Arrays and sparse matrices instead of a graph database</td><td>The whole graph fits in memory on a laptop, traversals are vectorised, and the project has no service to install.</td></tr>
<tr><td>Control edges keep their direction</td><td>Sanctions exposure flows from the controller to the controlled entity. Undirected search would treat every client of a busy nominee as exposed.</td></tr>
<tr><td>A benign lookalike for every planted typology</td><td>Without lookalikes any threshold would score perfectly and the benchmark would say nothing.</td></tr>
</table>
