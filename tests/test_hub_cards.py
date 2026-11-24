"""The cards of a space's repositories on the Hub: each dataset repository gets a README.md that says what it
holds, names the project, links to PhysicsHive and carries the tag physics-hive; the Space's card keeps the
metadata it does not manage."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

import hub

README = Path(__file__).resolve().parents[1] / "space" / "README.md"
REPOS = hub.repo_names("lab", "x")


def card(text: str) -> tuple[dict, str]:
    _, meta, body = text.split("---\n", 2)
    return yaml.safe_load(meta), body


@pytest.mark.parametrize("key", ["workspace", "traces", "sources", "chat_debug"])
def test_each_dataset_card_names_the_project_and_carries_the_tag(key):
    meta, body = card(hub.dataset_card(key, REPOS))
    assert meta["tags"] == [hub.CARD_TAG] and meta["viewer"] is False
    assert meta["pretty_name"].startswith("[PhysicsHive] x")
    assert "**x**" in body and hub.PROJECT_URL in body
    assert body.lstrip().startswith(f"# {meta['pretty_name']}")


def test_the_cards_link_the_repositories_of_the_project():
    _, body = card(hub.dataset_card("workspace", REPOS))
    assert hub.repo_url(REPOS["traces"]) in body and hub.repo_url(REPOS["sources"]) in body
    assert f"/spaces/{REPOS['space']}" in body
    _, body = card(hub.dataset_card("traces", REPOS))
    assert hub.repo_url(REPOS["workspace"]) in body and "does not guarantee" in body
    assert "~/.claude/CLAUDE.md" in body and "e-mail address" in body  # the harness's context stays in a trace


def test_the_space_card_keeps_the_metadata_it_does_not_manage():
    readme = ("---\ntitle: Physics Hive\nemoji: ⚛️\nsdk: docker\ntags: [physics-hive]\nmodels:\n- a/b\n"
              "hf_oauth: true\n---\n\n# Body\n")
    meta, body = card(hub.space_card(readme, "x", "Is X finite?"))
    assert meta["tags"] == ["physics-hive"] and meta["models"] == ["a/b"] and meta["hf_oauth"] is True
    assert meta["title"] == "[PhysicsHive] x" and meta["short_description"] == "Is X finite?"
    assert body == "\n# Body\n"
    # A card written before 0.6.0, titled "[Physics Hive] x": its title is replaced, not duplicated.
    old = hub.space_card(readme, "x", "Is X finite?").replace("[PhysicsHive] x", "[Physics Hive] x")
    card_text = hub.space_card(old, "x", "Is X finite?")
    assert card(card_text)[0]["title"] == "[PhysicsHive] x" and card_text.count("title:") == 1
    # The Space app's own README.md: every field it has survives, whatever the other fields are.
    original, _ = card(README.read_text(encoding="utf-8"))
    deployed, _ = card(hub.space_card(README.read_text(encoding="utf-8"), "x", "Is X finite?"))
    assert {k: v for k, v in deployed.items() if k not in ("title", "short_description")} == \
           {k: v for k, v in original.items() if k not in ("title", "short_description")}


class FakeHub:
    """Records the repositories created and the files uploaded; `fail_uploads` makes upload_file fail."""

    created: list = []
    uploads: dict = {}
    fail_uploads = False

    def whoami(self):
        return {"name": "me", "orgs": [{"name": "lab"}]}

    def repo_exists(self, repo_id, repo_type=None):
        return False

    def create_repo(self, repo_id, repo_type=None, private=None, **kwargs):
        FakeHub.created.append((repo_id, repo_type, private))

    def upload_file(self, path_or_fileobj, path_in_repo, repo_id, repo_type=None, commit_message=None):
        if FakeHub.fail_uploads:
            raise OSError("network down")
        FakeHub.uploads[(repo_id, path_in_repo)] = path_or_fileobj.decode()


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def fake_create(monkeypatch, tmp_path):
    """create_shared against a local bare repository that stands for the workspace repository on the Hub."""
    FakeHub.created, FakeHub.uploads, FakeHub.fail_uploads = [], {}, False
    for name, value in (("NAME", "tester"), ("EMAIL", "t@example.com")):
        monkeypatch.setenv(f"GIT_AUTHOR_{name}", value)
        monkeypatch.setenv(f"GIT_COMMITTER_{name}", value)
    bare = tmp_path / "hub.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "-q", str(bare), str(seed))
    (seed / ".gitattributes").write_text("*.bin filter=lfs\n")  # what the Hub puts in a new repository
    git(seed, "add", ".gitattributes")
    git(seed, "commit", "-q", "-m", "initial commit")
    git(seed, "push", "-q", "origin", "HEAD:main")
    url = hub.repo_url
    monkeypatch.setattr(hub, "repo_url", lambda repo_id: str(bare) if repo_id == REPOS["workspace"] else url(repo_id))
    monkeypatch.setattr(hub, "api", lambda: FakeHub())
    monkeypatch.setattr(hub, "whoami", lambda: FakeHub().whoami())
    monkeypatch.setattr(hub, "get_token", lambda: "hf_login")
    monkeypatch.setattr(hub, "deploy_space", lambda *args: None)
    monkeypatch.setattr(hub, "space_host", lambda space: None)
    return tmp_path, bare


def create(target: Path) -> None:
    def create_local(target, harnesses, chat_model, hub=None, leads=None):
        target.mkdir(parents=True)
        (target / "project.toml").write_text("[hub]\n")

    def first_commit(target, message):  # like init.first_commit: it adds only the paths it knows
        git(target, "add", "--", "project.toml")
        git(target, "commit", "-q", "-m", message)

    hub.create_shared(target, "lab", "x", ["claude"], "m", "none", create_local=create_local,
                      first_commit=first_commit, regen=lambda target: None, version="test")


def test_create_gives_every_dataset_repository_its_card(fake_create):
    tmp_path, bare = fake_create
    create(tmp_path / "ws")
    assert [(r, kind) for r, kind, _ in FakeHub.created] == [
        (REPOS[k], "dataset") for k in ("workspace", "traces", "sources", "chat_debug")]
    for key in ("traces", "sources", "chat_debug"):
        assert FakeHub.uploads[(REPOS[key], "README.md")] == hub.dataset_card(key, REPOS)
    # The workspace's card is in its first commit, which reached the Hub, and .gitattributes is not.
    files = git(bare, "ls-tree", "--name-only", "main").split()
    assert "README.md" in files and "project.toml" in files and ".gitattributes" not in files
    assert git(bare, "show", "main:README.md") == hub.dataset_card("workspace", REPOS)
    assert git(bare, "rev-list", "--count", "main") == "2\n"


def test_a_card_that_cannot_be_uploaded_only_warns(fake_create, capsys):
    tmp_path, bare = fake_create
    FakeHub.fail_uploads = True
    create(tmp_path / "ws")
    assert "could not write the card" in capsys.readouterr().err
    assert "README.md" in git(bare, "ls-tree", "--name-only", "main").split()


SOURCES_ON_HUB = ["README.md", ".gitattributes", "2401.00001/README.md", "2401.00001/main.tex"]


class SourcesHub:
    """The sources repository on the Hub, holding `files`. The fakes select files with huggingface_hub's own
    filter, as snapshot_download and upload_folder do; `downloads` counts the calls to snapshot_download."""

    def __init__(self, monkeypatch, files):
        import huggingface_hub

        self.files, self.downloads, self.sent = files, 0, []
        monkeypatch.setattr(huggingface_hub, "snapshot_download", self.snapshot_download)
        monkeypatch.setattr(hub, "api", lambda: self)

    def list_repo_files(self, repo_id, repo_type=None):
        if isinstance(self.files, Exception):
            raise self.files
        return list(self.files)

    def snapshot_download(self, repo_id, repo_type=None, local_dir=None, ignore_patterns=None):
        from huggingface_hub.utils import filter_repo_objects

        self.downloads += 1
        for path in filter_repo_objects(self.files, ignore_patterns=ignore_patterns):
            (Path(local_dir) / path).parent.mkdir(parents=True, exist_ok=True)
            (Path(local_dir) / path).write_text(f"{path} from the Hub\n")

    def upload_folder(self, folder_path, ignore_patterns=None, **kwargs):
        from huggingface_hub.utils import filter_repo_objects

        files = sorted(p.relative_to(folder_path).as_posix() for p in Path(folder_path).rglob("*") if p.is_file())
        self.sent.append(list(filter_repo_objects(files, ignore_patterns=ignore_patterns)))


def test_the_sources_card_stays_on_the_hub(tmp_path, monkeypatch):
    """The sources repository's README.md is its card: not downloaded into literature/sources/, nor sent back.
    A paper's own README.md, in its folder, goes both ways."""
    sources = SourcesHub(monkeypatch, SOURCES_ON_HUB)
    folder = tmp_path / "literature" / "sources"
    folder.mkdir(parents=True)
    (folder / "README.md").write_text("an old card, downloaded before the cards were skipped\n")
    hub.sync_sources_up(tmp_path, REPOS, "S1")
    assert sources.sent == []  # only the card: nothing to upload

    hub.sync_sources_down(tmp_path, REPOS)
    assert sources.downloads == 1
    assert (folder / "2401.00001" / "README.md").read_text() == "2401.00001/README.md from the Hub\n"
    assert (folder / "README.md").read_text().startswith("an old card")  # the card was not downloaded
    hub.sync_sources_up(tmp_path, REPOS, "S1")
    assert sources.sent == [["2401.00001/README.md", "2401.00001/main.tex"]]


def test_a_sources_repository_without_papers_is_not_downloaded(tmp_path, monkeypatch, capsys, caplog):
    """Only the Hub's .gitattributes and the card: no download, so huggingface_hub's warning that every file
    was ignored is not printed at each session start. A repository that cannot be listed only warns."""
    sources = SourcesHub(monkeypatch, [".gitattributes", "README.md"])
    with caplog.at_level("DEBUG"):
        hub.sync_sources_down(tmp_path, REPOS)
    assert sources.downloads == 0 and not (tmp_path / "literature").exists()
    assert capsys.readouterr() == ("", "") and caplog.records == []

    sources.files = OSError("network down")
    hub.sync_sources_down(tmp_path, REPOS)
    assert sources.downloads == 0
    assert "could not download paper sources" in capsys.readouterr().err
