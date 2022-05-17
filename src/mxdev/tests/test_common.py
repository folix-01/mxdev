from .. import vcs
from ..vcs import common
from unittest import mock
import pytest
import queue
import typing


def test_print_stderr(mocker):
    write_ = mocker.patch("sys.stderr.write")
    flush_ = mocker.patch("sys.stderr.flush")
    common.print_stderr("message")
    assert write_.call_count == 2
    assert flush_.call_count == 1


def test_version_sorted():
    expected = ["version-1-0-1", "version-1-0-2", "version-1-0-10"]
    actual = common.version_sorted([
        "version-1-0-10",
        "version-1-0-2",
        "version-1-0-1"
    ])
    assert expected == actual


def test_BaseWorkingCopy():
    with pytest.raises(TypeError):
        common.BaseWorkingCopy(source={})

    class TestWorkingCopy(common.BaseWorkingCopy):
        def checkout(self, **kwargs) -> typing.Union[str, None]:
            ...
        def status(self, **kwargs) -> typing.Union[typing.Tuple[str, str], str]:
            ...
        def matches(self) -> bool:
            ...
        def update(self, **kwargs) -> typing.Union[str, None]:
            ...

    bwc = TestWorkingCopy(source=dict(url="https://tld.com/repo.git"))
    assert bwc._output == []
    bwc.output("foo")
    assert bwc._output == ["foo"]

    assert bwc.should_update(offline=True) is False
    assert bwc.should_update(update="true") is True
    assert bwc.should_update(update="yes") is True
    assert bwc.should_update(update="false") is False
    assert bwc.should_update(update="no") is False
    with pytest.raises(ValueError):
        bwc.should_update(update="maybe")

    bwc = TestWorkingCopy(
        source=dict(
            url="https://tld.com/repo.git",
            update="false"
        )
    )
    assert bwc.should_update(update="true") is False


def test_yesno(mocker):
    class Input:
        question = ""
        answer = ""
        def __call__(self, question):
            self.question = question
            answer = self.answer
            if answer == "invalid":
                self.answer = ""
            return answer

    input_ = mocker.patch("mxdev.vcs.common.input", new_callable=Input)
    print_stderr_ = mocker.patch("mxdev.vcs.common.print_stderr")

    common.yesno(question="Really?")
    assert input_.question == "Really? [Yes/no/all] "

    common.yesno(question="Really?", all=False)
    assert input_.question == "Really? [Yes/no] "

    assert common.yesno(question="") is True
    assert common.yesno(question="", default=False) is False

    input_.answer = "y"
    assert common.yesno(question="") is True
    input_.answer = "yes"
    assert common.yesno(question="") is True

    input_.answer = "n"
    assert common.yesno(question="") is False
    input_.answer = "no"
    assert common.yesno(question="") is False

    input_.answer = "a"
    assert common.yesno(question="") == "all"
    input_.answer = "all"
    assert common.yesno(question="") == "all"

    input_.answer = "invalid"
    common.yesno(question="")
    print_stderr_.assert_called_with(
        "You have to answer with y, yes, n, no, a or all."
    )

    input_.answer = "invalid"
    common.yesno(question="", all=False)
    print_stderr_.assert_called_with(
        "You have to answer with y, yes, n or no."
    )


def test_get_workingcopytypes():
    assert common._workingcopytypes == dict()
    workingcopytypes = common.get_workingcopytypes()
    assert workingcopytypes == {
        'bzr': vcs.bazaar.BazaarWorkingCopy,
        'darcs': vcs.darcs.DarcsWorkingCopy,
        'fs': vcs.filesystem.FilesystemWorkingCopy,
        'git': vcs.git.GitWorkingCopy,
        'gitsvn': vcs.gitsvn.GitSVNWorkingCopy,
        'hg': vcs.mercurial.MercurialWorkingCopy,
        'svn': vcs.svn.SVNWorkingCopy
    }
    assert workingcopytypes is common._workingcopytypes


def test_WorkingCopies_process(mocker, caplog):
    exit = mocker.patch("sys.exit")
    worker = mocker.patch("mxdev.vcs.common.worker")

    wc = common.WorkingCopies(sources={}, threads=1)
    wc.process(queue.Queue())
    assert worker.call_count == 1

    wc.threads = 5
    wc.process(queue.Queue())
    assert worker.call_count == 6

    wc.threads = 2
    wc.errors = True
    wc.process(queue.Queue())
    assert exit.call_count == 1
    assert caplog.messages == ["There have been errors, see messages above."]


def test_WorkingCopies_checkout(mocker, caplog):
    class SysExit(Exception):
        ...

    class Exit:
        def __call__(self, code):
            raise SysExit(code)

    mocker.patch("sys.exit", new_callable=Exit)

    class TestWorkingCopies(common.WorkingCopies):
        def process(self, the_queue):
            ...

    wc = TestWorkingCopies(sources={})

    with pytest.raises(SysExit):
        wc.checkout(packages=[], update='invalid')
    assert caplog.messages == [
        "Unknown value 'invalid' for always-checkout option."
    ]
    caplog.clear()

    with pytest.raises(SysExit):
        wc.checkout(packages=[], submodules='invalid')
    assert caplog.messages == [
        "Unknown value 'invalid' for update-git-submodules option."
    ]
    caplog.clear()

    with pytest.raises(SysExit):
        wc.checkout(packages=['invalid'])
    assert caplog.messages == [
        "Checkout failed. No source defined for 'invalid'."
    ]
    caplog.clear()

    wc = TestWorkingCopies(sources=dict(
        package=dict(vcs="invalid")
    ))
    wc.checkout(packages=['package'])
    assert caplog.messages == [
        "Unregistered repository type invalid"
    ]
