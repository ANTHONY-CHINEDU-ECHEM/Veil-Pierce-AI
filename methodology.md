# Methodology

This page states exactly how each number is produced. Every threshold named here is a field of `veilpierce/config.py` and can be overridden from the command line.

## Shared definitions

A company is **shell like** when at least one of the following holds: it was dissolved within 730 days of incorporation, its accounts category is dormant, or it is at least 640 days old and has filed no accounts. A young active company that has not yet had to file is not shell like.

A director is **overseas** when the usual residence of the resolved person is outside the United Kingdom.

## Detector scores

All scores are clipped to the range 0 to 1.

<table>
<tr><th>Typology</th><th>Unit scored</th><th>Score</th><th>Flag when</th></tr>
<tr><td>Nominee director network</td><td>Resolved person with at least 25 director appointments</td><td>0.15 + 0.25 x volume + 0.45 x share of shell like companies + 0.15 x share of sole directorships, where volume rises on a log scale from 25 to 200 appointments. A company takes the highest score among its directors.</td><td>0.50 or more</td></tr>
<tr><td>Mass registration address</td><td>Resolved address with at least 60 companies</td><td>0.05 + 0.15 x volume + 0.55 x share of shell like companies + 0.25 x share of overseas directors, where volume rises on a log scale from 60 to 800 companies.</td><td>0.50 or more</td></tr>
<tr><td>Circular ownership</td><td>Company</td><td>0.95 when the company lies in a strongly connected component of size above one in the ownership graph (control records plus leak data edges).</td><td>0.50 or more</td></tr>
<tr><td>Sanctions proximity</td><td>Company</td><td>Confidence of the screening match multiplied by 0.75 for every control step beyond the first, searched up to 4 steps in the direction of control.</td><td>0.30 or more</td></tr>
<tr><td>Opaque offshore ownership</td><td>Company with a corporate controller and no natural person within 8 steps</td><td>0.10 + 0.75 x highest jurisdiction opacity weight upstream + 0.10 when the chain has two or more corporate links + 0.10 when the company is shell like, less 0.30 x (1 less the opacity weight) when the company files substantive accounts.</td><td>0.50 or more</td></tr>
<tr><td>Burst incorporation and phoenix activity</td><td>Company</td><td>For a batch of at least 5 companies formed within 7 days of each other by one director at one address with fewer than 60 companies: 0.15 + 0.10 x batch size (capped at 12) + 0.70 x share of shell like members. For a phoenix pair: 0.85. The higher of the two.</td><td>0.50 or more</td></tr>
</table>

A phoenix pair is a dissolved company and a second company that share a director and an address, where the second was incorporated between 30 days before and 120 days after the dissolution and the names without legal form have a similarity of at least 88 out of 100.

## Fusion

The fused risk score is a noisy OR over the six typology scores:

    risk = 1 less the product over typologies of (1 less weight x score)

with weights of 0.90 for nominee, 0.85 for address, 0.95 for circular, 1.00 for sanctions, 0.85 for opacity and 0.80 for burst and phoenix. The bands are Critical from 0.85, High from 0.65, Medium from 0.40 and Low below that. The alert threshold used in the evaluation is 0.50.

## Sanctions screening rules

<table>
<tr><th>Evidence</th><th>Outcome</th></tr>
<tr><td>Names align token by token, birth year and month agree</td><td>Score is the name similarity plus 0.04. Match when 0.86 or more.</td></tr>
<tr><td>Names align, birth year agrees and one side has no month</td><td>Score is the name similarity. Match when 0.86 or more.</td></tr>
<tr><td>Names nearly identical (similarity of 0.93 or more), birth year agrees, month differs</td><td>Score is the name similarity x 0.85. Review.</td></tr>
<tr><td>Names nearly identical (similarity of 0.93 or more), no date of birth on the source or on the list</td><td>Score capped at 0.80. Review, never a match.</td></tr>
<tr><td>One side has a middle name and the other does not</td><td>Raised for review only when year and month both agree.</td></tr>
<tr><td>Birth years differ</td><td>Not raised.</td></tr>
</table>

Token alignment requires every token of the shorter name to have a counterpart in the longer one, by equal transliteration key or Jaro Winkler similarity of at least 0.80. This stops two people who share forenames and differ in surname from scoring as similar. Name order may be rotated (surname first) and may not be shuffled.

## Verification rules

A narrative claim is kept only if all of the following hold.

1. It cites at least one item and every cited item exists in the case.
2. Every number in the claim appears in a cited item.
3. Every run of two or more capitalised words in the claim (which is how names appear) is found in a cited item.
4. Any risk band it states equals the band the detectors computed.
5. It does not assert guilt or a confirmed offence.
6. It does not echo instruction like text.

When fewer than 90 percent of the claims of a model narrative survive, the whole narrative is discarded and the offline composer writes the dossier. The audit block of the dossier records which narrator wrote it, how many model claims were removed and why.

## Evaluation protocol

* Ground truth is the set of labels recorded by the generator for each planted company, one column per typology.
* Detector precision and recall are computed per typology at the flag threshold. A company that carries several planted typologies counts for each.
* The comparison of systems uses the label "any planted typology" and reports average precision, area under the receiver operating curve, precision at the top 100 and 1,000, and recall within review budgets of 1, 5 and 10 percent of all companies.
* Entity resolution is scored with pairwise precision and recall over all record pairs.
* The supervised challenger is scored only on out of fold predictions from five grouped folds, with the resolved address as the group, so that companies sharing an address never appear on both sides of a split. It is trained on raw features and never sees a typology score.
* The label budget study hides a share of the positive labels during training, treats the hidden positives as negatives, and scores against the full truth.
* Each ablation removes one capability and recomputes the affected typology with everything else unchanged.
* The fabrication test takes one genuine claim from each sampled dossier, builds seven false variants from it, and counts how many the verifier rejects.

## What the benchmark does not show

The typologies are planted by the same author who wrote the detectors. High recall therefore shows that the pipeline recovers known structure through realistic noise (spelling variants, unresolved links, lookalikes). It does not show how the thresholds would perform on a live register, where base rates are unknown and labels would have to come from investigation outcomes. The loaders exist so that this recalibration can be done.
