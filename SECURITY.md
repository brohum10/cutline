# Trust boundaries

Cutline reads bounded local JSON and prints reports. It never sends traffic,
queries infrastructure, runs link IDs as commands, changes routing, or writes
files. Choose new filenames when redirecting output: the shell can overwrite
files even though the application does not write them directly.

Topology identifiers, capacities, and certificates can reveal private network
structure. Use synthetic or sanitized examples in public repositories. There
are no credentials or service connections required by this program.

Certificates prove equal mathematical flow/cut bounds under the supplied model.
They do not prove measurements are authentic, capacities are current, failures
are independent in reality, or failover can complete in time. SHA-256 identifies
the normalized input but is not a digital signature or sender authentication.
The standalone verifier checks one certificate, not an arbitrary surrounding
audit report or a person's interpretation of it.

Input dimensions are bounded, but complete reports and all scenario graphs are
processed in memory. Use OS quotas for untrusted workloads. Do not use this
offline tool as an automated deployment or safety-critical approval system
without separate model validation and operational controls.

If reporting a vulnerability, use private GitHub vulnerability reporting where
available. Do not include private topology data or secrets in public issues.
