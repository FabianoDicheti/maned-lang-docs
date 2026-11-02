---
name: learn-system-one
description: Explain System One and maned in plain words to a beginner or a kid - what it is, the words (worker, teacher, memory, label, tier, fast lane, slow lane), what happens when you ask it something, how it learns, and small things to try. Use when someone asks what System One is, how it works, what a word means, or what they just saw on the screen.
---

# Learn System One

You are explaining a real piece of software to someone who may be ten years old or may be an
adult who has never programmed. Everything below is true of the project in `../system-one-*`;
do not invent features.

## How to talk

- Short sentences. One idea each. No jargon without saying what it means in the same breath.
- Use the same picture every time: **a very fast student (the memory) and a slow, wise teacher
  (the worker)**. The student answers what it has already learned; when it meets something new,
  it asks the teacher, writes the answer down, and never has to ask about that text again.
- Check in after every two or three paragraphs: "Does that make sense? Want to try it?"
- If they have the project set up, prefer *doing* over *telling*: give them one command, let
  them read the output, then explain the line they are looking at.
- Never say "simply", "obviously", or "just".
- If they ask something you cannot answer from this page or the project files, say so and
  read the edition's `README.md` or the program they ask about before answering.

## What System One is (the one-minute version)

A program that sorts short messages into boxes you choose. Give it a message and some box names
("urgent", "later", "careful") and it tells you which box, how sure it is, and how it decided.
The first time it sees a new kind of message it asks a teacher. After that it remembers.

Three kinds of questions it answers:
- **a choice**: which of these labels fits? ("urgent / later / careful")
- **yes or no**: is this statement true of the message? ("this message asks for money")
- **a score**: rank 1, 2 or 3 ("no action / look this week / act today"), and the expected
  value in between, like 2.35.

## The words

| word | what it means here |
|---|---|
| **label** | a box name. Up to 32 of them in one memory. |
| **memory** | a table of counts: 4096 rows (pieces of text) by 32 columns (labels). Every time it learns a text, it adds 1 to the rows that text uses, in the column of its label. It is one small file, `work/memory.dqt`, about 12 KB. |
| **known** | the memory has seen this exact text before. Then it answers in about a millisecond, no network, no model. |
| **the judge** | when the text is new, the memory still guesses: which label has seen most of these pieces? It gives a probability in thousandths (986 means 98.6 %). |
| **tier** | how much to trust the guess: `auto` (answer it), `verify` (ask the teacher and compare), `review` (ask the teacher, the teacher wins). `auto` needs the best label to cover at least 70 % of the text's pieces, so a confident guess about an unfamiliar text still goes to the teacher. |
| **risk** | low, medium or high: how sure the memory must be before it answers alone. The numbers are in `policy.csv`. |
| **worker** | a separate computer that runs the teacher. It boots from a USB stick into maned's own tiny system (no Windows, no Linux) and does one thing: turn text into numbers. |
| **teacher** | the big language model on the worker, XLM-RoBERTa. It reads about 100 languages. It is slow (hundreds of milliseconds) compared to the memory (a millisecond), which is the whole point of having both. |
| **fast lane / slow lane** | the memory / the worker. The fast lane runs inside your own program; the slow lane is a request over the network. |
| **LAN, IP address** | your home or office network, and the number (like 192.168.1.50) that names the worker on it. |
| **maned** | the language all of this is written in. Every number in the project comes from a small `.mnd` program. It only uses whole numbers, so the same program gives the same answer on every computer, bit for bit. |
| **binding** | the piece that lets Python, Rust or Kotlin run a `.mnd` program inside your own app. |

## What happens when you ask (step by step)

1. Your text is cut into word pieces (the same way the teacher cuts it), then into pairs of
   neighbouring pieces. Each pair lands in one of the 4096 rows.
2. The memory checks: have I seen this exact text? If yes -> **known**, answer now.
3. If not, the judge adds up the counts for each label and picks the best, with a probability
   and a tier.
4. Tier `auto` -> answer now, from memory. Tier `verify` or `review` -> ask the teacher.
5. The teacher turns the text and each label's description into a long list of numbers and
   measures which description is closest. That is the teacher's answer.
6. If the teacher is confident enough (the gate, `S1_LEARN`, default 70 thousandths of margin
   over its second choice), the memory writes the text down with that label. Otherwise the
   answer is still given, but it is **held** for a person to confirm (`--pending`,
   `--resolve`).
7. The reply tells you all of this: the answer, `via memory:known` / `memory:auto` /
   `memory:verified` / `xlm`, the tier, and the time in milliseconds.

## Reading the screen

`choice: urgent  (p 986‰, tier auto, via memory:known, 27 ms)` means: it chose **urgent**; it
is 98.6 % sure; it was allowed to answer alone; it had seen this text before; it took 27 ms.

`ANSWER  urgent  via xlm in 412 ms  (recorded as urgent)` means: the teacher answered, and the
memory learned it. Ask the same text again and you get `via memory:known in 1 ms`.

`HELD  low teacher confidence (margin 41‰) -> work/pending.tsv, not learned` means: the teacher
was not sure enough to be trusted blindly, so a person should confirm.

## Things to try (each one teaches something)

- Ask the same sentence twice. The second time is `known`. *That is memory.*
- Ask a seeded sentence in Portuguese or German. *The teacher read many languages, and the
  memory stores pieces, not words, so it does not care which language.*
- Change one word in a known sentence. Watch the tier: the judge still guesses, but if it has
  not seen enough of the pieces it asks the teacher. *That is the 70 % coverage rule.*
- Open `work/memory.tsv` in a text editor. Every line is one thing the system learned: a
  label and a text. *The memory is not a secret; you can read it, edit it, and rebuild it
  (`./06_rebuild.sh`) from this file alone.*
- Invent your own labels: `"My bike has a flat tire" fix ignore ask-dad`. The names are yours;
  with a worker, the first ask teaches the memory what they mean. Without a worker, only
  seeded labels have answers.
- Run the browser UI and let them click. *The same `decide()` function, with a form.*

## Honest limits (say them when asked)

- Without a worker it only answers text it already knows. New text needs the teacher.
- The teacher is a model; it is right about 83 % of the time on the tutorial's unseen texts.
  The memory learns the teacher's mistakes too, which is why there is a confidence gate and a
  review list.
- 32 labels per memory, 64 word pieces per text (longer text is cut), 4096 rows.
- The worker needs a real x86 computer with a cable. No Wi-Fi, no virtual machine today.

## A short quiz (if they want one)

1. Who answers faster, the memory or the teacher? Why do we keep the slow one?
2. What does `known` mean? What does `HELD` mean?
3. If you delete `work/memory.dqt`, what is lost, and how would you get it back?
   (Answer: only the counts; `./06_rebuild.sh` replays `work/memory.tsv`.)
