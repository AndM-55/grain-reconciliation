# Decisions

## Second pass adjustments

1. **Weight discrepancy problem:** After a few manual calculations, I do indeed see that proportion of 0.4536 in many records I claimed to be unresolved. I should definitely treat the `lb` unit from the controllers as valid. Initially, I did notice the `unit = lb` on some of the controller unloads, which should have told me to convert the units, but instead I chose to interpret the brief extremely literally. In hindsight, this was a strange choice haha. I changed `normalize_controller_record()` to convert the units from the controller where appropriate.

2. **Brief and data disagree:** This ties in with the above. Initially I treated the brief as absolute, but I realize now I should trust the controllers more, since they will have been created by your talented embedded team. With this suggestion, I noted what you said in your first hypothetical question answer. Trust the data, and if a record says nothing, don't assume, but refer to the other things you have. I made a helper function `_find_cloud_record_by_id()` called during the normalization process to reconcile the one `controller_unload` that was missing the weight unit.

**First commit:** First commit was here

3. **Time:** Looking at a few examples, I can see the `unloaded_at` stamps are consistently 1 hour apart, with the cloud being ahead. Arguably, this was a total oversight on my end. I verified that each `field_id` had at least one load record that was exactly 1 hour behind its cloud counterpart, which confirmed all fields of interest are in the same time zone. Incidentally, I found that the first 3 `field_id` entries in `fields.json` were not found in the `controller_unloads` at all (this info will help me later I'm sure). I have changed the controllers to be assigned `-06:00` as the time zone, so now the times of controllers and cloud should agree. Then I used `datetime.fromisoformat` to compare the `updated_at` times, and the record with the more recent update wins.

4. **50kg tolerance:** I can see that a 'weight discrepancy' can actually be attributed to a valid edit, because (perhaps) some product was manually added to the unload instead of through the truck/sensor, and the farmer uses their mobile app (or something similar) to manually correct it. At this point in time I will tentatively assume that all relevant unloads come from fields in the same `-06:00` time-zone, and all `unloaded_at` for matched cloud and controller records will agree (I recognize this assumption may be unideal). With that assumption, every `updated_at` timestamp will be a perfectly valid way to decide on a winner for the reconciled record.

**second commit:** There are now only 12 records marked as unresolved, and there are 42 records marked as resolved by my output. The total weight is roughly `502650.4 kg`.

5. **Missing from master oversimplification:** Based on your suggestion I thought of 4 reasons, 3 of which are simple.

    **a.** trashed cloud records cause orphaned controller records to go in this bin

    **b.** Field ID 'discrepancies' are another reason these orphans end up here, where the controller mentiones a field ID not seen in `fields.json`.

    **c.** It's a valid unload and the cloud just didn't catch up yet

    The final reason was very sneaky: controller double unload (same `unloaded_at`, `field_id`, and `truck_id` but with 2 different unload IDs).

    I implemented logic to catch and display all of these.

**Third commit:** There are now only 7 records marked as unresolved, and there are 43 records marked as resolved by my output. The total weight is roughly `520203.0 kg`. I believe I can reach 45 reconciled unloads and ~550000 kg ~~for the following reason: in suggestion 6, you called attention to my autopopulation of `fields.json`. For the same reason I should not blindly pre-load `fields.json` into my database, I think I can make the claim that this mystery field from the controller does exist somewhere, but just doesn't happen to be in my `fields.json`. I think I should trust the data and insert these mystery fields into the fields table with their respective IDs and crops, but I'll set `name` and `area_ha` both equal to `"unknown"`~~. **(Fourth commit)** I misinterpreted your 6th point. I still trusted the data and inserted the new fields into the fields table with their respective IDs and crops, and set `name` and `area_ha` equal to `"New Field {new_field_count}"` and `-1.0` respectively. (I am a little unsure that -1.0 is an appropriate placeholder, but I did this to avoid making the fields schema more complicated. Please let me know your thoughts)

6. **Report and Field names:** Changed my query for the report, now the names of all the fields are displayed instead of the ids, but they are still sorted by id.

7. **Rerunning tests:** This is an odd one, I recall the test was working as expected at some point, but that has now changed on my end too. "Cannot operate on a closed database." Looked at some documentation/stack overflow to find out what it means for the database to be closed, then quickly found that when `test_weight_discrepancy_routing` called `process_unloads` the db would get closed at the end of that function. I must have thrown that in there before my final commit. From there, I made some adjustments to my mock database testing logic, now the tests all seem to work.

8. **More tests:** Regrettably I could not download the python file in the email, and outlook was down so I couldn't reach you. However, your description seemed to point at how my normalizer function may have been inadequate in making some records agree.

* new test 1: I have adjusted the normalization function to take in both types of records and convert their times both to UTC, and adjusted my normalization test to confirm that both records agree.

* new test 2: I also implemented my "would test next" idea but specifically tailored it to check that the orphan controller record is flagged if it shares the same field, truck, and unload time as another record.

* new test 3: Test to confirm that an orphaned controller record with an unknown field ID gets added to reconciled_unloads and that the fields table increases in size.

    Total of 3 tests, all changed from the last iteration.

## with even more time

I would hope to refactor some of my code, as it is a bit messy and counterintuitive in some places. I would also make a more in depth test suite and aim for code coverage. Additionally, I would ask you questions sooner since they gave me so much perspective without giving away the answer and learning experience.

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
