from experiments.co2full_function_similarity.evaluation.evaluate_reports import calculate_metrics


def test_calculate_metrics() -> None:
    predictions = [
        {"label": 1, "pred_label": 1},
        {"label": 1, "pred_label": 0},
        {"label": 0, "pred_label": 1},
        {"label": 0, "pred_label": 0},
    ]

    metrics = calculate_metrics(predictions, beta=2, total_target_queries=2)

    assert metrics["tp"] == 1
    assert metrics["fp"] == 1
    assert metrics["tn"] == 1
    assert metrics["fn"] == 1
    assert metrics["precision"] == 50.0
    assert metrics["recall"] == 50.0
