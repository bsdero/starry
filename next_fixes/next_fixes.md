
1.-[COMPLETE] Check models list if the context_size for the LLM is not available.
Does the model context_size appears in the standard API calls for a
conversation?
If not, get the context_size from the model list API call.

2.-[COMPLETE] If during the session the LLM makes questions or require feedback it must
   be done through the in-scroll components for that, not through the TUI
   components.

3.-[COMPLETE] Move the role "software engineer" or "software developer" to a default
   role included with starry. The role implemented is "assistant"
   (config/default.toml [agents.assistant]); prompt sourced from
   prompts/role_assistant.txt.

4.-[COMPLETE] Use a different system prompt for PLAN mode. You can get it from
   @prompts/plan_mode.txt

5.-[COMPLETE] Double check if we have an "/aboutme" option, where the user gives feedback
   about himself.

6.-Double check the command if /btw, /rewind are implemented

7.-[COMPLETE] Check the command /compact or /summarize it should summarize the context,
   and start a new conversation.

8.-implement the comands /new, /project, /branch, /add-dir, /focus, /goal,
   /recap, /review

9.-Add infrastructure and commands for the user to define workflow and
   commands.

10.-[COMPLETE] Fix the configuration directory in ~/.local/starry. We will use ~/.starry
   and a configuration scheme of directories an files pretty much the same
   than claude code.

11.-[COMPLETE] Add creation of a directories tree, similar with settings and configuration
specific for project directory, identical to ~/.local/starry, named .starry.
Files in `pwd`/.starry will overrid the setting in ~/.local/starry.

12.-Add the multichat option. This allows two or more agents to chat
one single conversation among all.

13.-[COMPLETE] BUGFIX: The context meter in the top bar shows always a current context
    length = 0. It should increase in each request/answer.

14.-[COMPLETE] The dialog that appears in "/role" option has a frame and the frame appears
    like it has been cut out, in both sides. Fix it.

15.-[COMPLETE] Remove spaces between the chat frames.

16.-check the names of the agents overrides role name. 

