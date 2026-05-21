PENDING ITEMS FOR DAVY CLI.

1.-[COMPLETE] Add support for Ollama providers.
2.-[COMPLETE] Add a configurator for custom providers, based in a OpenAI/Ollama interface. It will be available in the menu /setup, as
   "New provider", and new data for a custom OpenAI endpoint must be asked to the user. The user must provide a name for the
   custom provider, an endpoint URL, and a bearer token, using a default if the user leve it in blank.
   After that, the software must try a connection and show a menu of available models for the user to select.
3.-[COMPLETE] Add a new tool "calculator" for do math operations.
4.-[COMPLETE] When a new provider is selected, the model must be selected after the provider change, automatically.
5.-[COMPLETE] In the context counter in the top bar, the total capacity must be shown, like [ [current_tokens]/[context_size] : [percentage] ]
6.-[COMPLETE] Add a new command "/clear" for clear the context and reset tokens counter. The CLI must ask the user "This will reset the conversation, continue?"
   whether the user confirms or cancel the request, the CLI must show the adequate answer in a frame.
7.-[COMPLETE] Add a new command "/rewind" for remove the last message sent from context and its response, if any. The cli must show "Cancelled, what I will do instead?"
   The request to the LLM must be stopped.
8.-[COMPLETE] the key "Cancel" should be the exact same than "rewind".
9.-[COMPLETE] Add command "/summarize" for summarize the conversation. A file named "summary_[sessionID]_[date +%m%d%Y-%H%M%S].md" must be created.
 The user must be aware of this information with an adequate frame, and also an option of continue the conversation with that summary
 must be offered with the next options "1.-Continue as is. 2.-Clear all and start a new conversation with this summary".
10.-[COMPLETE] Add the function "autosummarize" which offers a summarization after 75% of the tokens count/context_size for this model.
A menu must be shown for the user, giving advice to summarize. This option is enabled by default, with 75% and it can
be changed with the submenu "summarize" where the user can select a different percentage or disable autosummarize.
11.-[COMPLETE] The command /role must be updated. A submenu must be added with the next options:
   A.-Set role: The user can change role of the current LLM.
   B.-Create role: The user can add the role by using this option. 
      The software must ask the user for the name of the role, temperature, description and
      other parameters for it, like system prompt.
   C.-Remove role: Remove the selected role. Ask for confirmation to the user.
   D.-Update role: Update parameters of the selected role.
   Basically this is a CRUD for roles.
   Use the recently added CLI floating dialogs library.
   The roles prompt should be added to the default system prompt. Make sure that, when we chose a role and start a conversation using a
   role, the default system prompt is still used. The role prompt should be added to the default system prompt and use that as system prompt
   for the roles. 
   "Create role" and "update role" should display the Default System prompt. The CLI needs to suggest the user that the prompt for the role 
   is appended to the default system prompt.
12.-[COMPLETE] Investigate what is happening with sessions in command /sessions. Those are not showing up. Also the /sessions command should display
   an options menu, with each session. The user can re-open and re-take the session where it was leaved.
13.-[COMPLETE] Explore support for vim style tabs and buffers, buttons, text fields input, multi-window buffer display, dialogs and other CLI elements.

PENDING ITEMS, BATCH 2
14.-[COMPLETE] Make sure the code for the LLM library is completely separated from the CLI.
15.-[COMPLETE] Edit default System prompt, temperature for default conversation. Add those to the /setup menu. The configuration must be updated.
16.-[COMPLETE] Add a new command "/buffers". This is a list of buffers to display. when one is selected, the buffer must be sent to the screen. The user can select freely
    which buffer to show and return to the chat conversation.
17.-[COMPLETE] Context buffer: at conversation start a "Context" buffer is created and registered in the buffer
    registry. It displays the full LLM context snapshot: session metadata (session ID, provider, model, role,
    mode, token usage), system prompt, world state, active skill injections, and conversation history with
    turn labels. The buffer refreshes automatically when the user switches to the Context tab (via Ctrl+Right/Left,
    Alt+N, or /buffer → Open buffer) and stays live — updating on each completed LLM turn while the tab is
    visible. Display format (Markdown or JSON) is selectable via /setup → "Context format" and persisted in
    user preferences. No /context command; the buffer is accessed through the standard buffer/tab system.
18.-Support for agents must be added. The agents would have their own name, role, model, provider, system prompt, temperature, tools and
    skills set. Also they would be callable by the user, and other agents and talk with any on demand.
    Conversations between current LLM and the agent must start as usual, and their own conversation context should be maintained by the software.
19.-A new command /agent must be added. The next options should be available:
    A.-Create: the user can create an agent by using this option. The software must ask the user for the name of the agent, allow role, model,
       provider selection, a text which will be appended to the system prompt provided by the role, temperature and other parameters for it,
       using the CLI. Prepare all for make the agents talk one to the other when needed, for future implementations.
    B.-List: the user can list the available agents
    C.-Remove: remove agent
    D.-Edit: change parameters.
    Basically this is a CRUD for agents, plus the next options.
    E.-Chat: open a empty conversation with an agent. Context of this conversation wont be saved. Command /close would close the conversation with the agent.
    F.-List active agents: if in a session the LLM call agents, they must be listed here, in a menu option.
    G.-Chat with active agents: list the active agents, and if the user selects one, a conversation
       with the agent will start, with the current context of the session. Extra context of this conversation wont be saved. Command /close would close
       the conversation with the agent.
    H.-Kill an active agent. List the active agents, kill the selected. A message should be sent to the LLM that the agent is not active anymore.
20.-Add a new tool "list_available_agents" for let the LLM knows what agents are available and the capacities.
21.-Add a new tool "call_agent", for the LLM to start a conversation with an agent. When that happens a new buffer with the chat between both should be created,
    for the user to monitor and review.
22.-Add a new tool "stop_agent" for let the LLM to stop an agent when is not needed anymore.
23.-Add a new tool "list_active_agents" for display active agents to the LLM.
24.-[COMPLETE] Add a menu "/stats" with the current session information: tokens used, number of agents, objects created and other information useful for the user.
25.-[COMPLETE] BUGFIX: double check the buffers with context, tools output and all are updated when they are shown to the user.
26.-[COMPLETE] Add a submenu "Provider" to the /setup menu, and move the options "Change Provider", "Change Model", "New Provider" from the /setup menu into this "Provider"
    submenu. the "Provider" submenu must have the next options in this order:
    A.-"New Provider" -with existing functionality.
    B.-"List providers" -show a providers list, thats all.
    B.-"Change Provider" -with existing functionality.
    C.-"Remove Provider" -a menu options with the providers must be shown. Whatever the user selects, a confirmation must be shown to the user and if user
       confirms deletion, the provider must be removed. If the current provider is functional and is selected to removal, the confirmation message to the
       user must emphatize that.
    D.-"List Models" -list available models, just that.
    E.-"Change Model" -with existing functionality.
27.-[COMPLETE] BUGFIX: when the user request something in the prompt, in the chat tab, the scroll must go the bottom of the content automatically and behave as usual.
    Things get messy when the scroll is moved by the user, with the keys, mouse wheel. Again, THE SCROLL DONT MOVE WHEN THE USER CLICKS THE ARROWS UP/DN OF THE
    SCROLL. FIX THAT.
28.-[COMPLETE] Analize if the setup.sh and install.sh scripts have sense. By now we will
    have a local install script only, for setup the software into $HOME directory
    of the user.
29.-[COMPLETE] Tweak the theme "jalisco" colors to look the most like the screenshot1.png file. DONT UPDATE ANY CODE, just theme colors. Do a backup first, we will
    rollback if I dont like it.
30.-[COMPLETE] Add support for llama.cpp provider.
31.-[COMPLETE] Add an option in the /setup menu, "about". It should display a dialog with fixed text, with the software description, version, developers team and
    contact information.
32.-[COMPLETE] Add an option in the /setup menu, "Set user personalization context". This option is an injection of user persona/identity to the system prompt, it will
    be appended to the end. We need to capture two data from the user:
    A.-User name or user self identification. It can be captured in a one line input text field.
    B.-Optional User profile or profession. It can be captured in a multiline input text field.
    An adequate input dialog text has already been used in the /setup -> providers menu.
33.-[COMPLETE] Add an option "/rename", to rename current session instead the stablished ID. A dialog with a one liner input text can be used. It should be unique.
34.-[COMPLETE] BUGFIX: why the sessions shown in the sessions menues look different than the real sessions ID used in line command? Whay are not the same?
35.-[COMPLETE] Lets work in a simple dialogs/TUI/CLI library based on the floating dialogs we have already. This library should be used exclusively for the TUI and
    it should support:
    -dialog in a rounded frame -have that already
    -Use of theme color        -have that already
    -Labels in the dialog      -have that already
    -Input text field in one line   -have that already
    -Input text field multiliner     -do we have it?
    -labeled Buttons in a rounded frame
    -options menu selection
    -toggle buttons selection -check marks may be a cross or a checked marks

    Behavior:
    - dialog must have the focus, always and no lose it. Other input with the intention to handle other elements not in the dialog are ignored except Ctrl+C -quit the agent-,
    - All the key press and combinations in an open dialog are ignored except escape, Ctrl+C, tab, and other predefined key combinations for the nature of the input.
       ( standard keys for input text fields, arrows for change options, enter for select, 'T' for toggle, escape and others. )
    - elements must be clickable.
    - Escape must cancel/close the dialog
    - Enter key press selects one option in an option menu. also in a text field, changes to the next elements if any, or sends the input.


36.-[COMPLETE] New feature. In the top tabs line, add a ballot box in a square -unicode U+2612 character- to the right. It should be clickable.
    It should close the current buffer on display, except "chat". A key [Ctrl+x] can be used to close it.
37.-[COMPLETE] In the prompt, all the commands start with "/". when an input of 4 or more characters matches with a command, run the command.
38.-[COMPLETE] Make all of the CLI options menues to work with the new floating dialogs CLI. Keep the conversations/chats menues in the scrollable 
window intact.  
39.-[COMPLETE] Move the /sessions menu to the new floating dialog CLI library.
40.-[COMPLETE] Move the /buffers menu to the new floating dialog CLI library
41.-[COMPLETE] Review all of the dialogs in the system. Make sure the content, helpy captions and so on fits in the dialog width. wrap the help captions to 
    the next lines, if thats the case. also check the options fit in the dialog. I can see the dialog options are too large. Make the dialog
    wider if options are larget. 
42.-[COMPLETE] If possible, in the tools menues, display a short description of the tools. 
43.-[COMPLETE] Remove buffers list option from /buffer menu.
44.-[COMPLETE] Remove /notify option
45.-[COMPLETE] /trace shows structured Tracer entries (turn#, type,
   latency_ms, tokens_used) while /buffer->Tool Output shows raw tool call I/O text.
   They serve different purposes; /trace is retained.
