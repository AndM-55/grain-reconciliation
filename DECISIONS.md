# Decisions

## Second pass adjustments

1) Weight discrepancy problem: after a few manual calculations, I do indeed see that proportion of 0.0453 in many records I claimed to be unresolved. I should definitely treat the lb unit from the controllers as valid. Initially, I did notice the weight field being different on some of the controller unloads, which should have told me to convert the units, but instead I chose to interpret the brief extremely literally. In hindsight, this was a strange choice haha. I changed normalize_controller_record() to convert the units from the controller where appropriate.

2) Brief and data disagree: This immediately ties in with the above. Initially I treated the brief as absolute, but I realize now I should trust the controllers more, since they will have been created by your talented embedded team. With this suggestion, I noted what you said in your first hypothetical question answer. Trust the data, and if a record says nothing, don't assume, but refer to the other things you have. I made a helper function _find_cloud_record_by_id() to reconcile the one controller_unload that was missing the weight unit.

3) 

## What I built

* I built a containerized application as described to reconcile unload records from two sources: the cloud and controllers in the field. This program takes the provided json files, creates schemas and a relational database to store and help process data, and reconciles the records, treating the cloud as the master decision maker that determines the final record that will be persisted in the database. The program processes the data, making decisions on which records will be deemed reconciled, and which will be deemed incomplete/irreconcilable. Given the command listed in the README will also print the summary data to the console. Finally, this application also has two included unit tests, and a proposal for another unit test to validate the program behaviour.

## Choices I made (and what I rejected)

* I chose to go with python and sqlite3 to keep things simple, as this seemed appropriate for the scope of the activity, as opposed to a heavier RDBMS. I was also drawn to python because it's quite easy to process JSON

* I decided not to drop the entire database schema every time the container started up, but rather I just deleted from the tables during runtime to get around duplicate insertions.

* My first thought was to ensure that two unloads with the same ID have a consistent enough weight to one another. The threshold I chose was 50KG, so if the weight difference between the cloud and controller is greater than 50KG, I would flag this record as an inconsistency. I am NOT ACTUALLY sure if this is the appropriate amount to flag in the farming business, but this is what intuitively stood out to me.

* I also decided to reject any unload records that were found in the controller source but not the cloud source. This is because I was treating the cloud as the master, which would decide whether a record is truly valid.

* Incidentally, I allowed standalone cloud records with NO matching controller records to be validated and reconciled. Again, I am unsure if this is the standard for agricultural practices, but if you were to tell me that’s a no-go, I’m sure it would be trivial to change this logic to accommodate such.

* I decided that as long as the unload ID matches from both sources, and the weight discrepancy is in an appropriate range, then this should be valid for a reconciliation, and I would not flag it as invalid, even if the time stamps are a different. Perhaps this is too broad an assumption, but with the local nature of the controller clock, I decided this may be okay to leave for simplicity.

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

## tests

* For test 1 I chose to test the sanitization of the controller records, ensuring that the function adequately and accurately formatted the record similarly to the cloud record. I chose this one becasue I wanted to be certain that the data from the controller could be reliably fitted to the same schema as the cloud records so that comparisons would be easier.
* for test 2 I chose to test that records found from both sources that had too great of a weight difference were flagged and put into the unresolved_unloads table. I think this was an important test because this decision was nested deep in the logic of this pipeline, and successfully verifying this made me much more confident that my solution was behaving as intended. It was also a good exercise for me to unit test with a mock database, because this type of testing is more challenging but crucially important for ensuring records agree with one another.
* Another test I would like to implement with more time would be to test that controller records with no matching cloud record are correctly placed in the unresolved table

## With another day I would

* take a closer look at the time stamps of these records and implement more logic for flagging unresolved unloads.
* In general, I would have liked to look into common practices and standards for agricultural operations in the context of data reconciliation. I would have liked to be very confident in saying that X amount of weight discrepancy is the hard limit, or perhaps to know whether time stamp differences must be contended with.
* Naturally, I would have liked to rely on AI less for this, and weigh more delicately what would be the ideal tech stack to use for this problem. Perhaps I would have even bene interested in learning some Laravel.

## other tools

* used docker to hopefully make it easy to run for anyone wanting to.
