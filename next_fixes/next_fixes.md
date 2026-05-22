
1.-Check models list it context_size for the LLM not available.
Does the model context_size appears in the standard API calls for a
conversation?
If not, get the context_size from the model list API call.

2.-Review the standard system prompts.
3.-Use a different system prompt for PLAN mode.
4.-Double check if we have an "/aboutme" option, where the user gives feedback
   about himself.
5.-Double check the command if /btw is implemented
6.-Check the command /compact or /summarize it should summarize the context,
   and start a new conversation.
7.-implement the comand /new
8.-Add infrastructure for the user to define workflow and commands.
