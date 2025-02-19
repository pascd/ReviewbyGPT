# ReviewbyGPT

---

<a rel="license" href="http://creativecommons.org/licenses/by-nc-nd/4.0/"><img alt="Creative Commons License" style="border-width:0" src="https://i.creativecommons.org/l/by-nc-nd/4.0/88x31.png" />

Welcome to WebGPTHandler, a Python handler for interacting with online GPT chats.

Author: Pedro Afonso Dias

### <a name="Description"></a>1. Index

---

* [Description](#Description)
* [Prerequisites](#Prerequisites)
* [Installation](#Installation)
* [Usage](#Usage)

### <a name="Description"></a>2. Description

---

WebGPTHandler is a Python package that automates interactions with online GPT chat interfaces using Selenium. It provides an easy-to-use interface for automating browser actions such as sending messages, handling user sessions, and retrieving chat responses.
### <a name="Prerequisites"></a>3. Prerequisites

---

This package has been tested on:

- Operating System: Ubuntu 24.04
- Python Version: 3.12+
- Browser Compatibility: Google Chrome with ChromeDriver

**Dependencies**:

Ensure the following are installed before using this package:

- Python 3.12+
- Google Chrome
- ChromeDriver

Install required Python dependencies:

```pip install selenium undetected-chromedriver fake-useragent```

### <a name="Installation"></a>4. Installation

---

1. Setup all prerequisites.
2. Clone the [WebGPTHandler](/) repository to a specified directory:

```bash
git clone https://github.com/pascd/WebGPTHandler.git
```
3. Install the package and its dependencies:

```bash
pip install .
```

### <a name="Usage"></a>5. Usage

#### <a name="example_case"></a>Example case

---

Here is a simple example on how to use the GPT interaction manager:

 ```python
 import sys
import os

# Dynamically add the root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from src import ChatGPTInteractionManager

if __name__ == "__main__":

    chatgpt_handler = ChatGPTInteractionManager()

    chatgpt_handler.launch_chatpgt_page()

    chatgpt_handler.login()

    while True:
        response = chatgpt_handler.send_and_receive(message=input("Prompt: "))
        print(response)
 ```

This example allows the establishment of a conversation with any GPT in specific with the ChatGPT, through CLI.

For other examples and GPT chats, may find some content in the [examples](examples) folder of this repository.

-----------------------------------------------------------------------------------------------------------------
<br />This work is licensed under a <a rel="license" href="http://creativecommons.org/licenses/by-nc-nd/4.0/">Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License</a>.
