from app.main import app


def test_frontend_wallet_and_snapshot_contract_is_published():
    schema = app.openapi()
    paths = schema["paths"]

    assert "get" in paths["/wallets"]
    assert "get" in paths["/wallets/{wallet_id}/summary"]
    assert {"get", "post"} <= set(paths["/wallets/{wallet_id}/snapshots"])
    assert "post" in paths["/snapshots"]
    assert "get" in paths["/snapshot-jobs"]
    assert "get" in paths["/snapshot-jobs/{job_id}"]

    wallet_summary = schema["components"]["schemas"]["WalletSummaryRead"]
    assert {
        "balance_usd",
        "balance_source",
        "last_snapshot_at",
        "balances_count",
        "top_assets",
    } <= set(wallet_summary["properties"])


def test_release_metadata_is_part_of_openapi_info():
    info = app.openapi()["info"]

    assert info["title"] == "py_wallet"
    assert info["version"]
