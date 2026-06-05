# Security Hardening Backlog — py_wallet

Items below are **not** part of Phase 3.1. Track and implement separately.

## py_wallet (application repo)

| Item | Priority | Notes |
| --- | --- | --- |
| CodeQL for Python | Medium | Separate workflow |
| Trivy image scan | Medium | After `docker-build`; scan `py_wallet:<sha>` |
| Pin GitHub Actions by commit SHA | Medium | Replace `@v6` tags gradually |
| pip-audit blocking | Low | After clean baseline and CVE triage |
| Bandit blocking | Low | After `.bandit` config is stable |
| Full-history Gitleaks in CI | Low | Only after manual audit is clean or commits are allowlisted |

## py_wallet-infra (infrastructure repo)

| Item | Priority | Notes |
| --- | --- | --- |
| Sealed Secrets (kubeseal) | Medium | After confirming controller in cluster |
| SOPS + age | Alternative | If Sealed Secrets controller is unavailable |
| JWT secret rotation runbook | High | `docs/jwt-secret-rotation.md` |
| Link from py_wallet README | High | After runbook is published |

### Sealed Secrets decision gate

```bash
kubectl get crd sealedsecrets.bitnami.com 2>/dev/null
kubectl get pods -n kube-system | grep sealed-secrets
```

If controller exists, prefer Sealed Secrets. Otherwise use SOPS or manual K8s Secret
(Phase 2 approach).

### Rotation runbook outline (infra repo)

1. Triggers: suspected leak, planned rotation, team offboarding
2. Impact: all access tokens invalid; users must re-login (no refresh tokens yet)
3. Steps: generate offline → update Secret → rollout restart → smoke login
4. Sealed Secrets path: re-seal → commit → Argo CD sync
5. Never log secret values; never disable app validation as a hotfix
