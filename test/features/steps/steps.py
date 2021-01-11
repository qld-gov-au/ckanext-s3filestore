from behave import step
from behaving.web.steps import *  # noqa: F401, F403
from behaving.personas.steps import *  # noqa: F401, F403
from behaving.web.steps.url import when_i_visit_url


@step('I go to homepage')
def go_to_home(context):
    when_i_visit_url(context, '/')


@step('I log in')
def log_in(context):

    assert context.persona
    context.execute_steps(u"""
        When I go to homepage
        And I click the link with text that contains "Log in"
        And I fill in "login" with "$name"
        And I fill in "password" with "$password"
        And I press the element with xpath "//button[contains(string(), 'Login')]"
        Then I should see an element with xpath "//a[contains(string(), 'Log out')]"
    """)


@step('I go to dataset page')
def go_to_dataset_page(context):
    when_i_visit_url(context, '/dataset')


@step('I go to organisation page')
def go_to_organisation_page(context):
    when_i_visit_url(context, '/organization')


@step('I go to register page')
def go_to_register_page(context):
    when_i_visit_url(context, '/user/register')
