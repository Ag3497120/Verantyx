# Commercial corpus candidates (primary-source audit, 2026-08-28)

This is an engineering rights gate, not legal advice.  Free download does not
mean commercial permission.  Code licences do not automatically license a
separately downloaded dataset, images inside a dataset, a human body model, or
third-party marks and designs.

## Adoptable foundation

| Source | Useful layer | Primary licence/status | Gate |
| --- | --- | --- | --- |
| [FreeSewing](https://github.com/freesewing/freesewing) | Parametric patterns and construction code | [MIT](https://raw.githubusercontent.com/freesewing/freesewing/develop/LICENSE) | Code and bundled material; preserve notice |
| [GarmentCode](https://github.com/maria-korosteleva/GarmentCode) | Panels, interfaces, stitches, measurements and JSON programs | [MIT](https://raw.githubusercontent.com/maria-korosteleva/GarmentCode/main/LICENSE) | Code and clearly bundled samples only; do not transfer the licence to GarmentCodeData |
| [The Met Open Access](https://www.metmuseum.org/hubs/open-access) | Historical garment images and metadata | CC0 for assets marked Open Access | Asset-level CC0 only |
| [Smithsonian Open Access](https://www.si.edu/openaccess/faq) | CC0 2D/3D textile and garment assets | CC0-marked assets may be shared, modified and used commercially | Asset-level CC0; separate personality/trademark review |
| [Poly Haven](https://polyhaven.com/license) | PBR textures, HDRIs and 3D assets | CC0; official FAQ permits AI training | Appearance only, not measured mechanics |
| [Wikimedia Commons](https://commons.wikimedia.org/wiki/Commons:Licensing) | Images, video, diagrams and scans | Per-file CC/PD terms | Record author, source, attribution, share-alike and jurisdiction per asset |
| [Objaverse](https://huggingface.co/datasets/allenai/objaverse/blob/main/README.md) | GLB assets and metadata | Collection metadata ODC-By; per-object licences vary | Admit only selected CC0/CC BY objects; reject NC and unknown |
| [fabrics-drape-data](https://github.com/virtualtextiles/fabrics-drape-data) | Textile mechanics interchange fields | [MIT](https://raw.githubusercontent.com/virtualtextiles/fabrics-drape-data/master/LICENSE) | Good schema seed; not a large calibrated material corpus |

## Partial or legal-review-only

- [Fashionpedia](https://fashionpedia.github.io/home/data_license.html): ontology
  and annotations are CC BY 4.0, but the project does not own the image
  copyrights.  Use annotations only unless each original image is cleared.
- [GarmentCodeData v2](https://www.research-collection.ethz.ch/handle/20.500.11850/690432):
  no commercial permission for the whole dataset was established from the
  distribution page. `UNKNOWN_LEGAL_REVIEW`.
- [MIT Fabric Properties Dataset](https://people.csail.mit.edu/klbouman/pw/projects/materialproperties/dataset.html):
  valuable wind videos and measurements, but no controlling commercial licence
  was found on the official page. `UNKNOWN_LEGAL_REVIEW`.
- [CLOTH3D](https://github.com/hbertiche/CLOTH3D): free registration is not a
  commercial licence. `UNKNOWN_LEGAL_REVIEW`.
- [CLOTH4D](https://github.com/AemikaChow/CLOTH4D): code and source-data terms
  differ; the source garment data is not a commercial foundation.
- [SewFactory licence issue](https://github.com/sail-sg/sewformer/issues/26):
  unresolved dataset-licence request. `UNKNOWN_LEGAL_REVIEW`.
- [DeepFashion](https://mmlab.ie.cuhk.edu.hk/projects/DeepFashion.html):
  non-commercial research restrictions make it unsuitable for the commercial
  route.

## Recommended construction

The lowest-rights-risk corpus is generated forward from cleared structure:

```text
MIT parametric pattern/structure code
  -> photoloset structure graph and typed pattern
  -> six-arm cross simulation
  -> 3D garment, masks, depth, normals and correspondence
  -> front/side/back images and motion sequences with CC0 appearance assets
```

Do not generate an image first and treat an AI-inferred pattern as ground truth.
Forward generation keeps pattern, seam graph, material parameters, mesh and
pixels bound to one digest and lineage.

Synthetic generation cannot replace real calibration for tensile curves,
bending, friction, damping, hysteresis, seam puckering, comfort, breathability,
factory feasibility, or the unknowable back of a single front image.  A small
self-measured reference set is required for those claims.

Every admitted source must pass `corpus_manifest_check`; the schema is
[`corpus-manifest.schema.json`](corpus-manifest.schema.json).
