from ved_backend.connections import describe_failure


def test_describe_failure_reports_the_innermost_error_of_a_task_group() -> None:
    refused = ConnectionRefusedError("All connection attempts failed")
    nested = ExceptionGroup(
        "unhandled errors in a TaskGroup", [ExceptionGroup("inner", [refused])]
    )
    assert describe_failure(nested) == "All connection attempts failed"


def test_describe_failure_names_an_error_without_a_message() -> None:
    assert describe_failure(TimeoutError()) == "TimeoutError"
