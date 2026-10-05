# Vendored factors

`ccf_aws_f584c54.json` was extracted **by script** from Cloud Carbon Footprint (Apache-2.0) at commit
`f584c549ee358d5980d36513267d007ecd3ee716`:

- `packages/aws/src/domain/AwsFootprintEstimationConstants.ts` — PUE, memory/network/storage
  coefficients, min/max watts per processor, replication factors, regional annual factors
- `packages/core/src/FootprintEstimationConstants.ts` — US NERC subregion factors
- `packages/aws/src/lib/AWSInstanceTypes.ts` — vCPU, memory, processor and GPU mapping
- `packages/core/src/compute/ComputeProcessorTypes.ts` — processor display names

Do not edit by hand. To update: re-extract from a newer commit into a **new** file named with the new
short SHA, update `EG` code to load it, re-run the golden tests in `docs/METHODOLOGY.md §6` and record
the change in an ADR. Keep the old file until the ADR is accepted.
