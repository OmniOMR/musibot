import pytest

from musibot.api.domain import MusicorpusPageRepository, PageNotFound


def test_a_created_page_is_owned_and_empty() -> None:
    repository = MusicorpusPageRepository()

    page = repository.create(owner="alice")

    assert page.owner == "alice"
    assert page.executions == {}
    assert repository.get(page.page_id) is page


def test_a_missing_page_raises() -> None:
    repository = MusicorpusPageRepository()

    with pytest.raises(PageNotFound):
        repository.get("aaaaaaaaaaaa")


def test_delete_removes_and_returns_the_page() -> None:
    repository = MusicorpusPageRepository()
    page = repository.create(owner="alice")

    assert repository.delete(page.page_id) is page
    assert repository.count() == 0
    with pytest.raises(PageNotFound):
        repository.get(page.page_id)


def test_executions_are_numbered_per_page_from_one() -> None:
    repository = MusicorpusPageRepository()
    page = repository.create(owner="alice")

    first = page.add_execution("hello-world", "1.0.0", {})
    second = page.add_execution("hello-world", "1.0.0", {})

    assert (first.execution_id, second.execution_id) == (1, 2)
    assert page.executions[1] is first


def test_execution_numbering_does_not_reset_across_pages() -> None:
    repository = MusicorpusPageRepository()
    page_a = repository.create(owner="alice")
    page_b = repository.create(owner="alice")

    page_a.add_execution("p", "1", {})
    execution_on_b = page_b.add_execution("p", "1", {})

    # Each page numbers from 1 independently.
    assert execution_on_b.execution_id == 1


def test_a_page_reports_a_running_execution() -> None:
    repository = MusicorpusPageRepository()
    page = repository.create(owner="alice")

    assert not page.has_running_execution()

    execution = page.add_execution("p", "1", {})
    assert page.has_running_execution()

    execution.state = "completed"
    assert not page.has_running_execution()
