# 🚀 BME 590 - Laboratory Automation Class Repository

Welcome to the official class repository for Fall 2026 BME 590: Laboratory Automation!

**Professor**: Emma Chory, Ph.D.

**Teaching Assistant:** Benjamin (Ben) Perry

---

This README will provide all the necessary steps to set up your computer for class assignments, tutorials, and projects. We will install all necessary tools, including Python and the `pylabrobot` library, which is the core module we will use to control laboratory equipment. 

Please follow these steps in order and if you run into any issues, please send an issue to the \#pylabrobot channel in slack! Additionally, you can contact Ben or Professor Chory.

---

## Step 1: Install Foundational Tools (VS Code & Git)

Before we can work with Python, we need a code editor and a version control system. [**If you already have these installed, you may skip to Step 2.**]

1. **Install VS Code**: This is our recommended code editor, or integrated development environment (IDE), for this class. Please install the version relevant to your operating system at the following link. After installation, you should be able to open Visual Studio Code on your computer. We ask, unless you know what you are doing, to stick with VS code for this class as it will make debugging IDE issues consistent.

    - [**Install Link**](https://code.visualstudio.com/)

If you have installed it properly, you should see a setup screen similar to the screenshot below:

![Screenshot of VS Code Setup Screen on Mac](/figs/vscode_ss.png)

From here, we recommend **creating a folder** somewhere on your computer (e.g. docs/classes/bme-590-fall/) to store your code and projects for this class. After cloning the repository (see **step 3**), you can open this repository in VS Code by simply **Open Folder -> \<path_to_folder_you_created\bme590-fall-2026>**

2. **Install Git**: This tool lets us download and manage the project code from GitHub. Additionally, although we will not make heavy use of version control in this class, managing versions of software as they evolve is critical in software engineering, especially when working on a team on a project that needs to be collaborative and reproducible (as science often is). If you are interested in reading more about Git, see [here](https://git-scm.com/book/en/v2/Getting-Started-What-is-Git%3F).
    - [**Install Link**](https://git-scm.com/downloads)
        - For Mac, open the **terminal** then install [brew](https://brew.sh/) if not installed, then follow the **Homebrew Git Install Instructions** on the link above.
        - For Windows users, it is **highly recommended** to install Windows Subsystem for Linux (WSL) first (see below) then follow the **Debian/Ubuntu Git Install Instructions**. To do this, first follow **Step 1.3** below, then return to install Git. But, if you wish to use Windows, utilize the **Click here to download** button on the Windows install page (not recommended).
        - To confirm you have installed Git successfully, run the following in either **PowerShell, WSL, or the Mac Terminal**. You should see something similar to `git version 2.XX.X`

            ```bash
            git --version
            ```

3. **(Windows Users Only) Install WSL**: The Windows Subsystem for Linux (WSL) lets you run Linux directly on Windows. It's highly recommended for a smoother experience overall. Most coding packages may work on Windows, but all coding packages (with extremely few exceptions) work on Linux. If you'd like to read more on WSL, see [here](https://learn.microsoft.com/en-us/windows/wsl/about). For more information on how to use WSL with VS Code (**recommended reading for Windows users!**), see [here](https://code.visualstudio.com/docs/remote/wsl)
    - Open **PowerShell as an Administrator** (search for PowerShell, right-click, and select "Run as administrator").
    - Run this single command:

        ```powershell
        wsl --install
        ```

    - After it finishes, **restart your computer**. When it reboots, it will ask you to create a username and password for your new Linux system. Remember these!
        - Optionally, do not set a password.
        - If you have **forgotten your WSL password**, see instructions on resetting it [here](https://superuser.com/questions/1829481/how-to-reset-my-wsl-ubuntu-password)
    - Finally, to use with VS Code, navigate within VS Code to **Extensions -> Search -> WSL -> Install** (it is the one authored by Microsoft). You can then use VS Code with the following pattern:

        1. Open WSL from Windows Explorer (this should open a terminal window)
        2. Using the change directory (`cd`) command, navigate to your projects folder [you may have to make this with the make directory command (`mkdir`)].
        3. Once in your target folder, simply run `code .` and VS Code will open.
        4. If you run into errors with this process, you can open VS Code **first** then **WSL** (i.e. the converse to this process just described above). This can happen if you have not yet installed the WSL extension in VS Code.

---

## Step 2: Install Conda for Python Management

Conda is a package manager that will install Python and all our required libraries in an isolated environment. Because different projects require different **versions** of different packages and Python, using the same set of software for all your projects will likely lead to **conflicts**. 

Conda (and other more modern package managers like [uv](https://docs.astral.sh/uv/)) allows us to create an individualized environmemt **specific to this class**, with its own version of Python, NumPy, PyLabRobot, and other packages that are independent from the other packages you may have installed on your system. **Again, if you already have conda installed, you may skip this step.**

1. **Download Miniconda**: We'll use Miniconda, a minimal installer for Conda.
    - [**Install Link**](https://www.anaconda.com/docs/getting-started/miniconda/install#quickstart-install-instructions)
    - **Windows**: Again, it is **highly recommended** to use **WSL**, in which case you can follow the Linux/WSL instructions two bullets down. However, if using Windows, navigate to the **Windows PowerShell** install option. Open **Windows PowerShell** and copy/paste the commands listed.
    - **macOS**: Navigate to the code block for your chip (the "M" series chips are "Apple silicon") and copy/paste the commands listed.
    - **Linux/WSL**: Navigate to the **Linux** tab and copy-paste the commands listed into your **WSL or Linux terminal**.
    - Make sure to enter `yes` when agreeing to the terms of service.

2. **Restart Your Terminal**: Close and reopen your terminal (or VS Code) for the changes to take effect.

3. **Test Conda:** Test your install by running the following command `conda --version`. At this point if you get an error along the lines of `conda command not found` then please raise an issue in slack or contact Ben.
    ```bash
        conda --version
    ```

---

## Step 3: Set Up the Project Environment

Now we will download the project code and create a dedicated Conda environment for it.

1. **Open Your Terminal**:
    - **Windows**: Open the **WSL terminal**. You can find it in your Start Menu (it will be named "Ubuntu" or similar).
    - **macOS/Linux**: Open the standard **Terminal** app.

2. **Clone the Project Repository**: Run the following command to download the project code.

    ```bash
    git clone https://github.com/chory-lab/bme590-fall-2026.git
    ```

    This will install to your parent directory. If you would like to install to a different folder, such as your desktop, navigate to a new directory. For example: 

   ```bash
    cd Desktop/
    ```

3. **Navigate into the Project Folder**:

    ```bash
    cd bme590-fall-2026
    ```

4. **Create and Activate the Conda Environment**: This command creates a new, clean environment named `lab-automation` with Python 3.13.

    ```bash
    conda env create -f environment.yaml
    conda activate lab-automation
    ```

    Your terminal prompt should now start with `(lab-automation)` and you are all set! **Note:** In order to easily use your environment within VS Code, You will need to install the **Python** extension. (More on this in section below).

   If you are using an **older Mac**, then you may run into a very specific bug where NumPy does not compile due to the lack of a high-enough version C++ compiler. If this happens to you contact Ben; you will need to uninstall and reinstall Xcode.

5. **Creating your own folder for assignments**: Now that you have your environment setup, it is good practice to **create a folder** that can hold your work-in-progess assignments for two reasons:
    - We may, at any point, update the workshops with new material or edits to fix bugs. If you `git pull` the repo while working on a workshop file, you may **unintentionally overwrite** your work, losing all progress.
    - If, for whatefver reason, you get your file completely messed up while working on it, it is easy to simply delete the file and copy over a fresh version to work. 

    Once you are in the `bme590-fall-2026` directory, run the following to create a directory for your assignments-in-progress:

    ```bash
    mkdir assignments
    ```

    Then, for **each lab**, simply **copy the workshop** from `/workshops` to `/assignments` via **VS Code** or the command line:

    ```bash
    cp workshops/<name_of_workshop>.ipynb assignments
    ```

    Now, make sure you are working and saving progress on the workshops you have copied over to `assignments/`. For all intents and purposes, this should be treated as your working directory.

      ```bash
    cd assignments
    ```

---

## Step 4. How to Select Environment from VS Code

1. **Install Extension**: Navigate to the left-hand panel to the **Extensions** and in the bar entitled "Search Extensions in Marketplace", search for the following packages and click **"Install"**.
    - **Python** - This extension will configure VS Code with several useful debugging, linting, virtual environment, and other tools for coding in Python.
        - Example: ![Python Language Extension Highlight on VS Code](/figs/python_ext.png)
        - A **linter** is a static code analysis tool used in software development to analyze source code and flag potential programming errors, bugs, stylistic issues, and suspicious constructs. 

    - **Jupyter** - The assignments in this class will make heavy use of **Jupyter Notebook**, which is an interactive coding environment (i.e. you can run individual "blocks" of code and interleave markdown text in assignment write-ups). Normally, you would run `jupyter notebook` from the command line in your proejct folder to open a browser-based editor; however, this extension allows you to open notebooks directly in VS Code.
        - Example: ![Jupyter Language Extension Highlight on VS Code](/figs/jupyter_ext.png)

    - **WSL (Windows Users Only)** - WSL maintains an entire sub-operating system (subsystem) with its own folders in Linux. Normally, to access these, you would need to open up WSL then navigate to your folder of interest, then open VS Code. This extension allows you to directly connect to your own machine's WSL from VS Code, essentially treating your Linux folders as a normal Windows directory.
        - Example: ![WSL Extension Highlight on VS Code](/figs/wsl_ext.png)

2. **Activate Conda Environment**: Once you have VS Code, Git, your VS Code extensions, and Conda installed and working on your computer, your project workflow will occur along the following steps:
    - **Starting from VS Code**
        - Open VS Code on Mac or Windows
        - Go to **Explorer -> Open Folder** and open your projects folder where you plan to store your work for this class. (ideally, this should be the repository foler `bme590-fall-2026`)
            - **WSL Users** - Follow the instructions [here](https://code.visualstudio.com/docs/remote/wsl) under **From VS Code** or use the command palette (Ctrl/Cmd + Shift + P) to select **WSL: Connect to WSL** to open your Linux folders in your WSL instance.
        - **Important:** Open the terminal in VS Code and run `git pull` to retrieve any updates to the course repo before beginning work.
        - Using the command palette (Ctrl/Cmd + Shift + P), search for **Python: Select Interpreter** and then navigate the options to select the **(lab-automation)** environment.
            - Example: ![Example in VS Code of Python Interpreter Drop Down Menu](/figs/python_int.png)
        - Open or create a **\.ipynb** or **\.py** file in your working directory to begin your coding!
            - A **.py** file is a standard Python file while **.ipynb** file is an interactive notebook. You likely will want to use the latter.
        - Once finished, make sure to save your work locally and exit VS Code.
    - **Starting from Terminal**
        - Open **WSL, PowerShell, or Mac Terminal** and navigate to your projects folder.
        - Activate your conda environment using `conda activate lab-automation`.
        - **Important:** Open the terminal in VS Code and run `git pull` to retrieve any updates to the course repo before beginning work.
        - Open your editor of choice (CLI editors such as Neovim/etc. are not recommended unless you are proficient) such as VS Code with the `code .` command.
            - You may optionally also use `jupyter notebook` to open a browser based editor instead of VS Code.
        - Similarly edit and save your files as you see fit, making sure to save your work.

---

## Step 5. Accessing Workshops

All of the relevant workshop documents can be found in the [workshops folder](./workshops). These Jupyter Notebook files contain all of the relevant information you will need for the exercises to work. If you have properly installed the **Jupyter Notebook** extension in VS Code, then these files should open no problem.

In this class, we encourage you to **try the above installation and run Pylabrobot locally** for several reasons:
1. If you are targeting a career in software engineering, environment setup teaches a lot about how software works together on different operating systems, and running into issues is one of the best ways to learn one of the untaught challenges with software engineering.
2. We would like as much of the class to be using **the same version of PLR and environment setup** to make troubleshooting easier.

---

## Step 6. Updating to the Latest Version

We are periodically improving the workshops, so to make sure you always have the most recent versions of the course materials and workshops:

- **From VS Code**
  - Open the integrated terminal in VS Code (``Ctrl+ `` on Windows/Linux, or ``Cmd+ `` on Mac).
  - Confirm that your terminal is running inside your project folder. If not, navigate there using `cd path/to/project`.
  - Ensure your conda environment is active with `conda activate lab-automation`.
  - Run:
    ```bash
    git pull
    ```
    This command will fetch and merge the latest updates from the course repository into your local copy.
  - If you encounter any merge conflicts, resolve them before continuing. Most often, this happens if you edited files that were also updated in the repo.
  - After pulling, re-open or refresh your Jupyter Notebook files to ensure you are working from the latest versions.

**Reminder: Always copy workshops into your `assignments/` folder**

To prevent overwriting your work when updating workshops, make sure you copy workshop files into your `assignments/` folder before working on them:

- For each lab, copy the relevant workshop into your assignments folder:
  ```bash
  cp workshops/<name_of_workshop>.ipynb assignments/
  ```

- Move into the assignments folder and work there:
  ```bash
  cd assignments
  ```

For all intents and purposes, treat `assignments/` as your working directory. This ensures you keep your progress safe while still being able to pull the latest updates to the original workshops.

---

## Help Resources & Troubleshooting

If you are having issues with installing or running PyLabRobot locally, please reach out to the TA for help.  **If you are still having issues (this sometimes happens with edge cases)**, we also provide [Google Colab versions](./colab_workshops) of every workshop in case you have issues with PLR installation. These Colab versions use a modified version of PLR that is compatible with colab **but have not been as thoroughly tested as the ones in [workshops](./workshops).**

To use with Colab, simply:
1. Download the `.ipynb` file for a given workshop.
2. Navigate to [Google Colab](https://colab.research.google.com/)
3. Navigate to **Upload -> Browse** and upload the workshop notebook.
4. Follow instructions in the notebook to complete the workshop.

If at any point in this process you run into troubles installing the requisite software, please follow the order of steps below:

1. Post an issue in the \#ed-discuss channel on slack. For anonymous question asking, use the `/anonymous` prefix before your message.
2. Email Ben (benjamin [dot] perry [at] duke [dot] edu) with the subject line **BME 590 Code Issues**
3. Come to office hours for Ben or Professor Chory, if scheduled.
4. Email Professor Chory (emma [dot] chory [at] duke [dot] edu).
