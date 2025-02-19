import datetime
import importlib
import os
import shlex
import subprocess
import sys
from contextlib import contextmanager
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner
from cookiecutter.utils import rmtree

try:
    import tomllib
except ImportError:
    from pip._vendor import tomli as tomllib


@contextmanager
def inside_dir(dirpath):
    """
    Execute code from inside the given directory
    :param dirpath: String, path of the directory the command is being run.
    """
    old_path = os.getcwd()
    try:
        os.chdir(dirpath)
        yield
    finally:
        os.chdir(old_path)


@contextmanager
def bake_in_temp_dir(cookies, *args, **kwargs):
    """
    Delete the temporal directory that is created when executing the tests
    :param cookies: pytest_cookies.Cookies,
        cookie to be baked and its temporal files will be removed
    """
    result = cookies.bake(*args, **kwargs)
    try:
        yield result
    finally:
        rmtree(str(result.project))


def run_inside_dir(command, dirpath):
    """
    Run a command from inside a given directory, returning the exit status
    :param command: Command that will be executed
    :param dirpath: String, path of the directory the command is being run.
    """
    with inside_dir(dirpath):
        return subprocess.check_call(shlex.split(command))


def check_output_inside_dir(command, dirpath):
    "Run a command from inside a given directory, returning the command output"
    with inside_dir(dirpath):
        return subprocess.check_output(shlex.split(command))


def load_pyproject(result):
    return tomllib.load(result.project.join('pyproject.toml').open('rb'))


def test_year_compute_in_license_file(cookies):
    with bake_in_temp_dir(cookies) as result:
        license_file_path = result.project.join('LICENSE')
        now = datetime.datetime.now()
        assert str(now.year) in license_file_path.read()


def project_info(result):
    """Get toplevel dir, project_slug, and project dir from baked cookies"""
    project_path = str(result.project)
    project_slug = os.path.split(project_path)[-1]
    project_dir = os.path.join(project_path, project_slug)
    return project_path, project_slug, project_dir


def test_bake_with_defaults(cookies):
    with bake_in_temp_dir(cookies) as result:
        assert result.project.isdir()
        assert result.exit_code == 0
        assert result.exception is None

        found_toplevel_files = [f.basename for f in result.project.listdir()]
        assert 'pyproject.toml' in found_toplevel_files
        assert 'python_boilerplate' in found_toplevel_files
        assert 'tox.ini' in found_toplevel_files
        assert 'tests' in found_toplevel_files


def test_bake_and_run_tests(cookies):
    with bake_in_temp_dir(cookies) as result:
        assert result.project.isdir()
        run_inside_dir('python -m unittest discover', str(result.project)) == 0
        print("test_bake_and_run_tests path", str(result.project))


def test_bake_with_specialchars(cookies):
    """Ensure that a `full_name` with double quotes does not break pyproject.toml"""
    with bake_in_temp_dir(
        cookies,
        extra_context={'full_name': 'name "quote" name'}
    ) as result:
        assert result.project.isdir()

        pyproject = load_pyproject(result)
        assert pyproject['project']['authors'][0]['name'] == 'name \"quote\" name'


def test_bake_with_apostrophe(cookies):
    """Ensure that a `full_name` with apostrophes does not break pyproject.toml"""
    with bake_in_temp_dir(
        cookies,
        extra_context={'full_name': "O'connor"}
    ) as result:
        assert result.project.isdir()

        pyproject = load_pyproject(result)
        assert pyproject['project']['authors'][0]['name'] == "O'connor"


# def test_bake_and_run_travis_pypi_setup(cookies):
#     # given:
#     with bake_in_temp_dir(cookies) as result:
#         project_path = str(result.project)
#
#         # when:
#         travis_setup_cmd = ('python travis_pypi_setup.py'
#                             ' --repo audreyr/cookiecutter-pypackage'
#                             ' --password invalidpass')
#         run_inside_dir(travis_setup_cmd, project_path)
#         # then:
#         result_travis_config = yaml.load(
#             result.project.join(".travis.yml").open()
#         )
#         min_size_of_encrypted_password = 50
#         assert len(
#             result_travis_config["deploy"]["password"]["secure"]
#         ) > min_size_of_encrypted_password


def test_bake_without_travis_pypi_setup(cookies):
    with bake_in_temp_dir(
        cookies,
        extra_context={'use_pypi_deployment_with_travis': False}
    ) as result:
        result_travis_config = yaml.load(
            result.project.join(".travis.yml").open(),
            Loader=yaml.FullLoader
        )
        assert "deploy" not in result_travis_config
        assert "python" == result_travis_config["language"]
        # found_toplevel_files = [f.basename for f in result.project.listdir()]


def test_bake_without_author_file(cookies):
    with bake_in_temp_dir(
        cookies,
        extra_context={'create_author_file': False}
    ) as result:
        found_toplevel_files = [f.basename for f in result.project.listdir()]
        assert 'AUTHORS.rst' not in found_toplevel_files
        doc_files = [f.basename for f in result.project.join('docs').listdir()]
        assert 'authors.rst' not in doc_files

        # Assert there are no spaces in the toc tree
        docs_index_path = result.project.join('docs/index.rst')
        with open(str(docs_index_path)) as index_file:
            assert 'contributing\n   history' in index_file.read()

        # Check that
        manifest_path = result.project.join('MANIFEST.in')
        with open(str(manifest_path)) as manifest_file:
            assert 'AUTHORS.rst' not in manifest_file.read()


def test_make_help(cookies):
    with bake_in_temp_dir(cookies) as result:
        # The supplied Makefile does not support win32
        if sys.platform != "win32":
            output = check_output_inside_dir(
                'make help',
                str(result.project)
            )
            assert b"check code coverage quickly with the default Python" in output


def test_bake_selecting_license(cookies):
    license_strings = {
        'MIT license': 'MIT ',
        'BSD license': 'Redistributions of source code must retain the ' +
                       'above copyright notice, this',
        'ISC license': 'ISC License',
        'Apache Software License 2.0':
            'Licensed under the Apache License, Version 2.0',
        'GNU General Public License v3': 'GNU GENERAL PUBLIC LICENSE',
    }
    for license, target_string in license_strings.items():
        with bake_in_temp_dir(
            cookies,
            extra_context={'open_source_license': license}
        ) as result:
            assert target_string in result.project.join('LICENSE').read()

            pyproject = load_pyproject(result)
            assert 'license' in pyproject['project']


def test_bake_not_open_source(cookies):
    with bake_in_temp_dir(
        cookies,
        extra_context={'open_source_license': 'Not open source'}
    ) as result:
        found_toplevel_files = [f.basename for f in result.project.listdir()]
        assert 'pyproject.toml' in found_toplevel_files
        assert 'LICENSE' not in found_toplevel_files

        pyproject = load_pyproject(result)
        assert 'license' not in pyproject['project']


def test_using_pytest(cookies):
    with bake_in_temp_dir(
        cookies,
        extra_context={'use_pytest': True}
    ) as result:
        assert result.project.isdir()

        test_file_path = result.project.join(
            'tests/test_python_boilerplate.py'
        )
        text = test_file_path.read()
        assert "import pytest" in text
        # Test the new pytest target
        run_inside_dir('pytest', str(result.project)) == 0

        pyproject = load_pyproject(result)
        assert any(dep.startswith('pytest==') for dep in pyproject['project']['optional-dependencies']['dev'])


def test_not_using_pytest(cookies):
    with bake_in_temp_dir(
        cookies,
        extra_context={'use_pytest': False}
    ) as result:
        assert result.project.isdir()
        test_file_path = result.project.join(
            'tests/test_python_boilerplate.py'
        )
        lines = test_file_path.readlines()
        assert "import unittest" in ''.join(lines)
        assert "import pytest" not in ''.join(lines)

        pyproject = load_pyproject(result)
        assert not any(dep.startswith('pytest==') for dep in pyproject['project']['optional-dependencies']['dev'])


# def test_project_with_hyphen_in_module_name(cookies):
#     result = cookies.bake(
#         extra_context={'project_name': 'something-with-a-dash'}
#     )
#     assert result.project is not None
#     project_path = str(result.project)
#
#     # when:
#     travis_setup_cmd = ('python travis_pypi_setup.py'
#                         ' --repo audreyr/cookiecutter-pypackage'
#                         ' --password invalidpass')
#     run_inside_dir(travis_setup_cmd, project_path)
#
#     # then:
#     result_travis_config = yaml.load(
#         open(os.path.join(project_path, ".travis.yml"))
#     )
#     assert "secure" in result_travis_config["deploy"]["password"],\
#         "missing password config in .travis.yml"


def test_bake_with_no_console_script(cookies):
    context = {'command_line_interface': "No command-line interface"}
    result = cookies.bake(extra_context=context)
    project_path, _, project_dir = project_info(result)
    found_project_files = os.listdir(project_dir)
    assert "cli.py" not in found_project_files

    pyproject = load_pyproject(result)

    assert 'scripts' not in pyproject['project']


def test_bake_with_console_script_files(cookies):
    context = {'command_line_interface': 'Click'}
    result = cookies.bake(extra_context=context)
    _, project_slug, project_dir = project_info(result)
    found_project_files = os.listdir(project_dir)
    assert "cli.py" in found_project_files

    pyproject = load_pyproject(result)

    assert 'scripts' in pyproject['project']
    assert project_slug in pyproject['project']['scripts']
    assert pyproject['project']['scripts'][project_slug] == f'{project_slug}.cli:main'


def test_bake_with_argparse_console_script_files(cookies):
    context = {'command_line_interface': 'Argparse'}
    result = cookies.bake(extra_context=context)
    _, project_slug, project_dir = project_info(result)
    found_project_files = os.listdir(project_dir)
    assert "cli.py" in found_project_files

    pyproject = load_pyproject(result)

    assert 'scripts' in pyproject['project']
    assert project_slug in pyproject['project']['scripts']
    assert pyproject['project']['scripts'][project_slug] == f'{project_slug}.cli:main'


def test_bake_with_console_script_cli(cookies):
    context = {'command_line_interface': 'Click'}
    result = cookies.bake(extra_context=context)
    _, project_slug, project_dir = project_info(result)
    module_path = os.path.join(project_dir, 'cli.py')
    module_name = '.'.join([project_slug, 'cli'])
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    runner = CliRunner()
    noarg_result = runner.invoke(cli.main)
    assert noarg_result.exit_code == 0
    noarg_output = ' '.join([
        'Replace this message by putting your code into',
        project_slug])
    assert noarg_output in noarg_result.output
    help_result = runner.invoke(cli.main, ['--help'])
    assert help_result.exit_code == 0
    assert 'Show this message' in help_result.output


def test_bake_with_argparse_console_script_cli(cookies, capsys):
    context = {'command_line_interface': 'Argparse'}
    result = cookies.bake(extra_context=context)
    _, project_slug, project_dir = project_info(result)
    module_path = os.path.join(project_dir, 'cli.py')
    module_name = '.'.join([project_slug, 'cli'])
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    with patch('sys.argv'):
        cli.main()

    captured = capsys.readouterr()
    result = captured.out
    assert f'Replace this message by putting your code into {project_slug}' in result

    with pytest.raises(SystemExit, match='0'):
        cli.main(['--help'])

    captured = capsys.readouterr()
    result = captured.out
    assert 'show this help message' in result


@pytest.mark.parametrize('use_black, expected', [(True, True), (False, False)])
def test_black(cookies, use_black, expected):
    """Test for validating the Black code formatter integration and configuration.

    Checks:
    - Validates the presence of 'black' in the 'pyproject.toml' file based on the 'use_black' param.
    - Verifies the presence of 'black' in the pyproject.toml based on the 'use_black' param.
    - Verifies the presence of 'black' in the '.pre-commit-config.yaml' file based on the 'use_black' value.
    """
    with bake_in_temp_dir(
        cookies,
        extra_context={'use_black': use_black}
    ) as result:
        assert result.project.isdir()

        pyproject = load_pyproject(result)
        assert any(dep.startswith('black==')
                   for dep in pyproject['project']['optional-dependencies']['dev']) is expected
        assert ('black' in pyproject['tool']) is expected

        pre_commit_config = result.project.join('.pre-commit-config.yaml')
        assert ('id: black' in pre_commit_config.read()) is expected


@pytest.mark.parametrize('use_mypy, expected', [(True, True), (False, False)])
def test_mypy(cookies, use_mypy, expected):
    """Test for validating the MyPy integration and configuration.

    Checks:
    - Validates the presence of 'black' in the 'pyproject.toml' file based on the 'use_mypy' param.
    - Verifies the presence of 'mypy' in the pyproject.toml based on the 'use_mypy' param.
    - Verifies the presence of 'mypy' in the '.pre-commit-config.yaml' file based on the 'use_mypy' value.
    """
    with bake_in_temp_dir(
        cookies,
        extra_context={'use_mypy': use_mypy}
    ) as result:
        assert result.project.isdir()

        pyproject = load_pyproject(result)
        assert any(dep.startswith('mypy==') for dep in pyproject['project']['optional-dependencies']['dev']) is expected
        assert ('mypy' in pyproject['tool']) is expected

        pre_commit_config = yaml.safe_load(result.project.join('.pre-commit-config.yaml').read())
        repo_names = [repo['repo'] for repo in pre_commit_config['repos']]
        assert ('https://github.com/pre-commit/mirrors-mypy' in repo_names) is expected


@pytest.mark.parametrize('command_line_interface, expected', [
    ('Click', True), ('Argparse', False), ('No command-line interface', False)
])
def test_click_is_optionally_added_as_mypy_dependency(cookies, command_line_interface, expected):
    """Test for validating the 'click' dependency is added to MyPy if both of them are chosen."""
    with bake_in_temp_dir(
        cookies,
        extra_context={'command_line_interface': command_line_interface, 'use_mypy': True}
    ) as result:
        pre_commit_config = yaml.safe_load(result.project.join('.pre-commit-config.yaml').read())
        additional_dependencies = None

        for repo in pre_commit_config['repos']:
            if repo['repo'] == 'https://github.com/pre-commit/mirrors-mypy':
                additional_dependencies = repo['hooks'][0]['additional_dependencies']

        assert additional_dependencies is not None, 'Could not find mypy hook'
        assert ('click' in additional_dependencies) is expected
