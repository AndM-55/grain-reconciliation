# Decisions

## What I built

* I built a containerized application as described to reconcile unload records from two sources: the cloud and controllers in the field. This program takes the provided json files, creates schemas and a relational database to store and help process data, and reconciles the records, treating the cloud as the master decision maker that determines the final record that will be persisted in the database. The program processes the data, making decisions on which records will be deemed reconciled, and which will be deemed incomplete/irreconcilable. Given the command listed in the README will also print the summary data to the console. Finally, this application also has two included unit tests, and a proposal for another unit test to validate the program behaviour.

## Choices I made (and what I rejected)

* chose to go with python and sqlite3 to keep things simple, as this seemed appropriate for the scope of the activity, as opposed to a heavier RDBMS.

* I decided not to drop the entire database schema every time the container started up, but rather I just deleted from the tables during runtime to get around duplicate insertions.

* My first thought was to ensure that two unloads with the same ID have a consistent enough weight to one another. The threshold I chose was 50KG, so if the weight difference between the cloud and controller is greater than 50KG, I would flag this record as an inconsistency. I am NOT ACTUALLY sure if this is the appropriate amount to flag in the farming business, but this is what intuitively stood out to me.
* I also decided to reject any unload records that were found in the controller source but not the cloud source. This is because I was treating the cloud as the master, which would decide whether a record is truly valid.
* Incidentally, I allowed standalone cloud records with NO matching controller records to be persisted. Again, I am unsure if this is the standard for agricultural practices, but if you were to tell me that’s a no-go, I’m sure it would be trivial to change this logic to accommodate such.
* I decided that as long as the unload ID matches from both sources, and the weight discrepancy is in an appropriate range, then this should be valid for a reconciliation, and I would not flag it as invalid. Perhaps this is too broad an assumption, but with the local nature of the controller clock, I decided this may be okay to leave for simplicity.

## Things in the brief or data that didn’t add up, and what I did

### The brief

* It seemed that the JSON files were not accessible in the given PDF doc, so I did the best with what I could see to still show the learning outcomes of this exercise.
* Additionally, I sent out an email to request the full data.

### The data

* The project description asserted that all weights for the data are in KG, so instead of performing a conversion where a controller record said unit = lb, I decided to ignore this attribute and assume it was already in kg, and simply map the new attribute name to the same value during sanitization

## AI Tools I used

* I used Google Gemini to assist me in this exercise. I intended to reach an end product where I could clearly display my decision-making around the actual task, rather than getting caught up in the details of tools and syntax I haven’t extensively used before.
* Some instances where Gemini let me down is when it would suggest an implimentation that was not consistent with the activity description. For example, it would suggest many intricate details about unit conversion, etc., without considering the description of the activity. It would also frequently forget that I wanted to run this project with docker and persistently suggest dependency installations, as well as forget my schema design.
* Other than that, it was quite helpful for scoping out this problem and deciding on the tech stack, and it was certainly helpful for suggesting how to best utilize Python from a syntax standpoint.

## other tools

* used docker to hopefully make it easy to run for anyone wanting to.
