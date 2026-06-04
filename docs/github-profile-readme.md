# Eitan Divone

I build AI systems and applied machine learning projects with a focus on architecture, execution, and technical depth.

I am a high school student graduating in 2026 and a participant in Magshimim, a three-year advanced program in programming, data science, and machine learning.

## Background

- Magshimim participant
- Strongest in Python, machine learning, and AI systems
- Fluent in English
- Build projects independently beyond formal coursework and program requirements

## What I Build

- agent systems that connect model reasoning to real tools and operating environments
- applied machine learning projects built as full technical workflows, not only isolated experiments
- backend-heavy software where architecture, reliability, and clear control flow matter

## Featured Projects

### [EmploAI](https://github.com/mighty-epic/emploai)

EmploAI is an agentic computer-control system designed to execute real tasks on a live machine rather than only generate text. It receives tasks remotely, reasons over the current state of the environment, selects tools, executes actions, observes the results, and continues until the task is completed or requires intervention.

The project is structured as a system, not a single script. Its main pieces include:

- interface layer through Telegram, a CLI, and supporting backend services
- provider-agnostic agent loop with support for multiple LLM providers
- tool execution layer for files, shell commands, web access, browser control, and desktop control
- observation layer using screenshots, browser snapshots, and OCR
- memory layer for persistent context across sessions
- scheduler for recurring jobs and long-running automation

In practice, EmploAI can move between different execution environments during the same task. It can use DOM-level browser automation when that is reliable, switch to a real Chrome session when login state matters, and fall back to OCR and desktop input when normal browser control is not enough. That design choice is central to the project: reliable computer-use systems need multiple fallback paths rather than one idealized automation layer.

Tech:

- Python
- FastAPI
- Selenium
- OpenCV
- Pillow
- Tesseract OCR
- Linux VPS deployment
- OpenAI, Anthropic, and Gemini APIs

### NYC Real Estate ML

This project is an end-to-end machine learning and data science workflow built on real NYC property data. The goal was not only to train a model, but to work through the full CRISP-DM process: understanding the problem, cleaning real-world data, engineering useful features, comparing models, evaluating performance, and presenting results clearly.

Main areas of work:

- exploratory data analysis and data quality review
- preprocessing and feature engineering
- model comparison using XGBoost and TabPFN
- synthetic data experiments with CTGAN
- evaluation through R2 and RMSE
- iterative improvement documented through notebooks and presentations

Current project materials:

- [Presentation](https://docs.google.com/presentation/d/1G-Mh_W7NVhqQdHJG1eryFyqZgYve9DAXPVDE_P0mdO8/edit?usp=sharing)
- [Colab Notebook 1](https://colab.research.google.com/drive/1p-fXIKnW1az6yLsG4teXaHkRi9KD3aZp?usp=sharing)
- [Colab Notebook 2](https://colab.research.google.com/drive/1q_crZiBp1KeqYjHfpu7RiJP9-SwWkxe5?usp=sharing)
- [Colab Notebook 3](https://colab.research.google.com/drive/1KGT_iGyEdXvqcpIt_RAoz1D9aXEDSK22?usp=sharing)
- [Colab Notebook 4](https://colab.research.google.com/drive/1C9z7i94Bxq7SokSsySil7Zt5JQQGpx5u?usp=sharing)

A dedicated repository for this project is being organized so the materials can be presented in a cleaner engineering format.

## Technical Skills

### Languages

- Python
- SQL
- JavaScript / TypeScript

### AI And Machine Learning

- supervised learning
- feature engineering
- model evaluation
- XGBoost
- TabPFN
- CTGAN
- prompt and tool-based agent design

### Systems And Backend

- FastAPI
- REST and WebSocket services
- Linux
- task scheduling
- multi-session runtime design

### Automation And Vision

- Selenium
- browser automation
- Tesseract OCR
- OpenCV
- Pillow

### Tools

- Git
- Google Colab
- Jupyter notebooks

## Contact

- GitHub: [mighty-epic](https://github.com/mighty-epic)
