# grain-reconciliation readme

## running and populating the db

I developed this program in VScode using WSL (Windows subsystem for Linux) Ubuntu terminal, and I gave docker a go too.

clone from my public repository like so. \
`git clone https://github.com/AndM-55/grain-reconciliation`

to reconcile the data and populate the database, I ran the command: \
`docker-compose up --build`

## viewing results

to view the results without re-running the reconciliation, I rand the command: \
`docker-compose run --rm app python main.py report` \
which simply prints the results in a tabular form to the console

## testing

to run my unit tests, I ran the command: \
`docker-compose run --rm app pytest`

## other notes/docker compose

I wanted to get tocker working for this submission, and it certainly worked on my end when running the above commands through my WSL terminal, though I did run into some weirdness around the commands not working if 'docker-compose' did not have the hyphen in it. Hopefully none of this becomes an issue for you.
