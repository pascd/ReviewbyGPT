import sys
import os
import time

# Dynamically add the root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from webgpthandler.scripts.chatgpt_interaction_manager import ChatGPTInteractionManager

if __name__ == "__main__":

    chatgpt_handler = ChatGPTInteractionManager()

    chatgpt_handler.launch_chatpgt_page()

    chatgpt_handler.login()

    while True:
        response = chatgpt_handler.send_and_receive(message=input("Prompt: "))
        print(response)

        time.sleep(2)
        chatgpt_handler.new_chat()
