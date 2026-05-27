# Resume Evidence: Chemprop Arrhenius Hydrogen-Abstraction Kinetics

## One-Line Project Summary

Built a Chemprop-based graph neural network workflow for predicting forward and
reverse modified-Arrhenius parameters for hydrogen-abstraction reactions, using
reaction-aware molecular graph learning, geometry/QM-derived atom features,
temperature-grid rate evaluation, hyperparameter optimization, and paper-grade
reproducibility artifacts.

## What This Repository Does

This repository extends Chemprop v2 from general molecular property prediction
into a domain-specific kinetics modeling system for elementary hydrogen
abstraction reactions:

```text
A-H + B -> A + B-H
```

The model predicts a full modified-Arrhenius triplet for both forward and
reverse directions:

```text
k(T) = A * T^n * exp(-Ea / RT)
```

That means the project is not only predicting one scalar property. It learns a
compact physical parameterization of a temperature-dependent reaction rate
curve, then evaluates the implied rate constants across a temperature grid.

The Arrhenius-specific logic lives under `arrhenius/`, while the vendored
Chemprop core provides the message-passing neural network backbone, molecular
graph featurization, training utilities, and CLI infrastructure.

## Evidence of Technical Scope

### Machine Learning and Deep Learning

- Implemented a multi-component message-passing neural network for reaction
  kinetics, where each reaction is represented through multiple molecular
  components rather than a single molecule.
- Extended Chemprop with custom Arrhenius prediction heads that output
  `[A, n, Ea]` parameter triplets.
- Supported separate forward and reverse prediction heads, allowing the model
  to learn directional kinetics while still sharing reaction-level graph
  representations.
- Implemented order-aware, order-invariant, bidirectional, antisymmetric, and
  learned pooling modes for donor/acceptor reactant ordering.
- Added an Arrhenius layer that converts predicted parameters into `ln k(T)`
  over a temperature grid, enabling supervision directly on physically relevant
  rate constants.
- Used robust multi-target losses, including Smooth L1/Huber losses on scaled
  Arrhenius parameters and optional MSE supervision on temperature-dependent
  `ln k(T)`.
- Used target transformations and inverse transforms, including log scaling for
  `A` and Yeo-Johnson-style scaling for activation energies.
- Built HPO and model-selection workflows around cross-validation, holdout
  evaluation, pinned hyperparameters, and reproducible train/validation/test
  splits.
- Added deep ensemble export and prediction workflows for epistemic uncertainty
  estimation.

Relevant implementation areas:

- `arrhenius/modeling/module/pl_rateconstant_dir.py`
- `arrhenius/modeling/module/model_core.py`
- `arrhenius/modeling/module/losses.py`
- `arrhenius/modeling/nn/layers.py`
- `arrhenius/modeling/nn/predictor.py`
- `arrhenius/training/hpo/`

### Graph Neural Networks and Molecular Representation

- Worked with directed message passing neural networks (D-MPNNs), the core
  architecture used by Chemprop for molecular property prediction.
- Modeled reactions as multi-component graph inputs, rather than treating the
  reaction as plain text or a fixed descriptor vector.
- Supported Chemprop CGR-style reaction modeling for graph-only retraining from
  the published CSV.
- Integrated atom-level and bond-level features into molecular graphs.
- Added geometry-aware edge features based on 3D structure:
  - radial basis expansions of interatomic distances
  - angle features encoded with sine/cosine
  - dihedral/torsion features encoded with sine/cosine
  - masks to distinguish missing geometric information from valid zero values
- Built feature modes that compare baseline graph-only learning against
  geometry-only, local atom features, RAD features, and combined RA+Geom modes.

Relevant implementation areas:

- `arrhenius/featuriser/molecue.py`
- `arrhenius/featuriser/habnet_featurizer.py`
- `arrhenius/training/hpo/feature_modes.py`
- `chemprop/nn/message_passing/`
- `chemprop/featurizers/`

### Chemistry and Kinetics Concepts

- Modeled hydrogen abstraction reactions with explicit donor, acceptor, donor-H,
  acceptor-H, donor-neighbor, and acceptor-neighbor roles.
- Predicted modified Arrhenius parameters:
  - pre-exponential factor `A`
  - temperature exponent `n`
  - activation energy `Ea`
- Evaluated rate constants across chemically relevant temperature ranges,
  including 300-3000 K workflows.
- Used forward and reverse kinetics for the same elementary reaction, enabling
  analysis of directional consistency.
- Worked with transition-state theory plus tunneling-corrected rates
  (`TST+T`) from Arkane.
- Used Eckart tunneling corrections in the dataset provenance.
- Compared ML predictions against RMG template-rate-rule estimates and NIST
  experimental kinetics data.
- Analyzed model error by reactive atom type, donor/acceptor pairing,
  hybridization, and pi-adjacency at reactive sites.
- Performed detailed-balance / equilibrium-constant consistency analysis by
  comparing predicted `k_fwd / k_rev` against `Keq(T)` derived from DFT/Arkane
  thermochemistry.

Relevant repository evidence:

- `data/README.md`
- `data/reactions.csv`
- `data/oof_predictions.csv`
- `data/rmg/reactions_batched_kinetics.yml`
- `data/nist/`
- `arrhenius/analysis/r3_11_keq.py`
- `data/figures/r3_11_keq_summary.txt`

### Quantum Chemistry and Scientific Data Provenance

- Built preprocessing workflows that connect quantum-chemistry artifacts to ML
  training data.
- Parsed Gaussian frequency outputs for atom-level QM-derived quantities:
  - Mulliken charge (`q_mull`)
  - APT charge (`q_apt`)
  - force magnitude (`f_mag`)
- Supported labeled SDF construction from Gaussian and ORCA optimization logs.
- Built atom-level geometry/QM feature CSVs from reaction manifests.
- Worked with ARC and Arkane outputs from a high-throughput reaction kinetics
  pipeline.
- Used high-level single-point energy provenance from DLPNO-CCSD(T)-F12.
- Preserved atom mapping and reaction role labels so chemical identity is
  consistent across reactants, products, and transition states.

Relevant implementation areas:

- `arrhenius/preprocessing/README.md`
- `arrhenius/preprocessing/QM_RAD_PIPELINE_SPEC.md`
- `arrhenius/preprocessing/build_labeled_pair_sdf.py`
- `arrhenius/preprocessing/build_atom_with_geom_qm.py`
- `arrhenius/preprocessing/gaussian_qm.py`
- `arrhenius/preprocessing/build_published_dataset.py`

### Evaluation, Reproducibility, and Research Engineering

- Packaged a compact published dataset of 1,665 reactions for graph-only
  benchmarking without requiring raw Gaussian/Arkane artifacts.
- Preserved paper-era out-of-fold predictions, best configuration files,
  checkpoints, and figure-generation scripts.
- Added notebooks for paper result reproduction, NIST comparison, representative
  reaction analysis, and live inference from a shipped checkpoint.
- Built pinned retraining paths for reproducing the selected RA+Geom model with
  fixed hyperparameters and fixed split indices.
- Added scripts for reviewer-response analyses, including rotor reruns, fit
  quality diagnostics, and detailed-balance consistency.
- Maintained install and environment documentation for reproducible execution
  across GPU-backed environments.

Relevant repository evidence:

- `arrhenius/paper/`
- `arrhenius/analysis/README.md`
- `arrhenius/training/hpo/WORKFLOW.md`
- `checkpoints/pinned_best-best.ckpt`
- `data/best_config.json`
- `environment.yml`
- `bin/install.sh`

## Concrete Skills Demonstrated

### ML / AI Skills

- Graph neural networks for molecular and reaction property prediction
- Directed message passing neural networks
- Multi-component neural architectures
- Multi-target regression
- Physics-informed neural network layers
- Temperature-conditioned loss design
- Feature engineering for graph models
- Representation learning for chemical reactions
- Robust regression with Huber/Smooth L1 losses
- Target scaling, inverse transforms, and numerical stability
- Cross-validation and holdout testing
- Hyperparameter optimization with structured search spaces
- Deep ensembles for epistemic uncertainty
- Model checkpointing, inference packaging, and reproducibility

### Chemistry / Quantum / Kinetics Skills

- Modified Arrhenius kinetics
- Hydrogen abstraction reaction mechanisms
- Forward/reverse elementary reaction modeling
- Transition-state theory
- Tunneling-corrected rate coefficients
- Eckart tunneling corrections
- Activation energy interpretation
- Equilibrium constants and detailed balance
- RMG atom types and rate-rule baselines
- ARC/Arkane kinetics workflows
- Gaussian and ORCA log handling
- SDF-based molecular structure workflows
- Atom mapping across reactants, products, and transition states
- Geometry-derived descriptors: distances, angles, and dihedrals
- QM-derived atom descriptors: charges and force magnitudes

### Software Engineering Skills

- Python package architecture
- PyTorch and Lightning model development
- RDKit-based molecular preprocessing
- Chemprop extension and customization
- CLI workflow design
- Data validation and schema documentation
- Scientific data packaging
- Reproducible research workflows
- Notebook-to-script analysis reproducibility
- Model artifact management
- Config-driven training and HPO
- Test fixtures for scientific preprocessing
- Maintaining a forked/vendor ML framework while isolating domain-specific code

## Resume Bullet Options

Use or adapt these depending on the role.

### Machine Learning Engineer

- Extended Chemprop v2 with a reaction-specific graph neural network pipeline
  for hydrogen-abstraction kinetics, predicting forward and reverse
  modified-Arrhenius parameter triplets rather than single scalar properties.
- Implemented custom PyTorch/Lightning modules with directional prediction
  heads, Arrhenius `ln k(T)` supervision, robust multi-target losses, target
  scaling, and multiple donor/acceptor order-invariance strategies.
- Built reproducible HPO, cross-validation, pinned-split retraining, checkpoint
  export, and ensemble inference workflows for chemistry-focused graph neural
  network models.
- Engineered molecular graph features from 3D geometry and QM outputs,
  including distance RBFs, angle/dihedral encodings, atom role labels, partial
  charges, and force magnitudes.

### Computational Chemistry / Scientific ML

- Developed a scientific ML workflow for predicting temperature-dependent
  reaction rate coefficients for hydrogen abstraction reactions from molecular
  graph structure and geometry/QM-derived descriptors.
- Integrated ARC/Arkane-derived TST+Eckart tunneling kinetics with graph neural
  network training targets for 1,665 curated reactions.
- Evaluated model behavior against RMG template-rate-rule estimates, NIST
  kinetics data, reactive atom-type stratifications, and detailed-balance
  consistency via `k_fwd/k_rev` vs. DFT-derived `Keq(T)`.
- Built preprocessing tools to transform Gaussian/ORCA logs and SDF structures
  into atom-mapped, role-labeled, ML-ready reaction datasets.

### Research Software Engineer

- Packaged a paper-grade research codebase with reproducible datasets,
  checkpoints, notebooks, analysis scripts, installation paths, and documented
  workflows for retraining and inference.
- Isolated domain-specific Arrhenius kinetics extensions from the upstream
  Chemprop framework, preserving maintainability while adding specialized
  modeling, preprocessing, and evaluation layers.
- Built data and model workflows supporting graph-only baselines, geometry/QM
  feature modes, hyperparameter optimization, locked test evaluation, and
  uncertainty-aware ensemble export.

## Interview Talking Points

- Why predicting `[A, n, Ea]` is harder and more useful than predicting a rate
  at one temperature.
- How the Arrhenius layer connects neural outputs to physical rate constants
  and enables supervision on `ln k(T)`.
- Why donor/acceptor ordering matters for H-abstraction reactions and how the
  model handles order awareness versus invariance.
- How graph neural networks represent molecular structure and why 3D geometry
  can add information that plain SMILES-derived graphs miss.
- How Gaussian/ORCA, ARC, Arkane, RMG, and NIST data connect into a single
  scientific ML workflow.
- How forward/reverse predictions can be checked against detailed balance and
  thermodynamic equilibrium constants.
- How to distinguish epistemic uncertainty from aleatoric uncertainty when
  using deep ensembles.
- What was required to turn a research prototype into a reproducible package:
  data schemas, pinned configs, fixed splits, checkpoints, notebooks, scripts,
  and install docs.

## Strongest Evidence Artifacts

| Artifact | What it demonstrates |
|---|---|
| `arrhenius/modeling/module/pl_rateconstant_dir.py` | Custom Lightning model for forward/reverse Arrhenius GNN prediction |
| `arrhenius/modeling/nn/layers.py` | Physics-aware Arrhenius layer converting parameters to `ln k(T)` |
| `arrhenius/featuriser/molecue.py` | Geometry-aware molecular graph featurization |
| `arrhenius/training/hpo/` | HPO, CV, feature modes, model construction, evaluation, prediction |
| `arrhenius/preprocessing/` | Gaussian/ORCA/SDF/QM preprocessing pipeline |
| `data/README.md` | Dataset provenance, schema, and chemical conventions |
| `arrhenius/paper/` | Paper result reproduction notebooks |
| `arrhenius/analysis/` | Figure and reviewer-response analysis scripts |
| `checkpoints/pinned_best-best.ckpt` | Shipped trained checkpoint for live inference |

## Short Portfolio Description

`chemprop_arrhenius` is a scientific ML project for predicting
temperature-dependent hydrogen-abstraction reaction kinetics. It extends the
Chemprop graph neural network framework with Arrhenius-specific model heads,
physics-aware rate-constant supervision, reaction-role labeling, geometry and
QM atom features, HPO/CV workflows, uncertainty-aware ensemble prediction, and
paper-grade reproducibility artifacts. The project demonstrates practical
experience at the intersection of graph neural networks, computational
chemistry, quantum-chemistry data pipelines, and production-quality research
software engineering.
