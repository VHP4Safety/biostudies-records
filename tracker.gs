/**
 * @OnlyCurrentDoc
 * Keeps the BioStudies rows of the RO inventory tracker as tracker.json describes them.
 * Lives at https://github.com/VHP4Safety/biostudies-records: paste it under Extensions > Apps Script, run install() once,
 * and paste it again whenever tracker.json changes.
 */
const API = "https://www.ebi.ac.uk/biostudies/api/v1/";
/** tracker.json, which a test keeps identical to this copy. */
const MODEL = {
  "sheet" : "1UfcQIZaGBU11n6jZtI6BmpCBZLy8IbWMBKr5pAqUwq0",
  "gid" : 1572306711,
  "collection" : "vhp4safety",
  "columns" : {
    "title" : {
      "from" : "Title"
    },
    "Description" : {
      "from" : "Description"
    },
    "identifier" : {
      "from" : "accno",
      "prefix" : "https://www.ebi.ac.uk/biostudies/vhp4safety/studies/"
    },
    "privateLink" : {},
    "caseStudy" : {
      "from" : "Case study",
      "many" : true,
      "default" : "Other"
    },
    "regulatoryQuestion" : {
      "from" : "Regulatory Question",
      "many" : true,
      "labels" : {
        "reg_q_1a" : "Q1",
        "reg_q_1b" : "Q2",
        "reg_q_2a" : "Q1",
        "reg_q_2b" : "Q2",
        "reg_q_3a" : "Q1",
        "reg_q_3b" : "Q2"
      },
      "default" : "N/A"
    },
    "workPackage" : {},
    "workflowStep" : {
      "from" : "Process Flow Step",
      "many" : true
    },
    "status" : {},
    "embargoDate" : {},
    "releaseMetadata" : {
      "from" : "ReleaseDate"
    },
    "license" : {
      "from" : "License"
    },
    "hasMetadata" : {},
    "hasToxTemp" : {},
    "hasROCrate" : {
      "from" : "files",
      "present" : "Yes",
      "default" : "No"
    },
    "contactPerson" : {},
    "partnerCode" : {},
    "type" : {},
    "isReviewed" : {},
    "FAStatus (platform.vhp4safety.nl)" : {},
    "FAIRscore" : {},
    "notes" : {}
  }
};

function install() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger("sync").timeBased().everyHours(1).create();
  sync();
}

function get(url) {
  return JSON.parse(UrlFetchApp.fetch(url).getContentText());
}

/** What tracker.json wants in the tracker row of a record; bsmeta.py holds the same rules. */
function expected(study, row, today) {
  const facts = {};
  for (const attributes of [study.section.attributes || [], study.attributes || []]) {
    const found = {};
    for (const a of attributes) (found[a.name] = found[a.name] || []).push(String(a.value || "").trim());
    Object.assign(facts, found);
  }
  facts.accno = [study.accno || ""];
  facts.files = (study.section.files || []).flat().map(f => f.path);
  const out = {};
  for (const [column, spec] of Object.entries(MODEL.columns)) {
    if (!spec.from) continue;
    let values = (facts[spec.from] || []).filter(v => v).map(v => (spec.labels || {})[v] || v);
    if (values.length && spec.present) values = [spec.present];
    values = [...new Set(values)].map(v => (spec.prefix || "") + v);
    if (!values.length) values = [spec.default || ""];
    out[column] = spec.many ? values.join(", ") : values[0];
  }
  const embargo = row.embargoDate || "";
  const passed = !embargo || (/^\d{4}-\d{2}-\d{2}$/.test(embargo) && embargo <= today);
  const have = row.status || "";
  out.status = facts.files.length && passed ? "Public" : have === "Public" ? "Shared" : have;
  return out;
}

function sync() {
  const sheet = SpreadsheetApp.getActive().getSheets().find(s => s.getSheetId() === MODEL.gid);
  const table = sheet.getDataRange().getDisplayValues().map(cells => cells.map(c => c.trim()));
  const head = table[0];
  const at = name => {
    const c = head.indexOf(name);
    if (c < 0) throw new Error("The tracker has no column " + name);
    return c + 1;
  };
  Object.keys(MODEL.columns).forEach(at);
  const rowOf = {};
  table.forEach((cells, i) => {
    const acc = cells[at("identifier") - 1].match(/S-VHPS\d+/);
    if (acc) rowOf[acc[0]] = i;
  });
  const today = Utilities.formatDate(new Date(), "Europe/Amsterdam", "yyyy-MM-dd");
  const set = text => [...new Set(text.split(", "))].sort().join("\n");
  // ponytail: one page of 100 studies; page through when the collection outgrows it
  for (const hit of get(API + MODEL.collection + "/search?pageSize=100").hits) {
    if (!(hit.accession in rowOf)) rowOf[hit.accession] = table.push(head.map(() => "")) - 1;
    const i = rowOf[hit.accession];
    const row = Object.fromEntries(head.map((name, c) => [name, table[i][c]]));
    const want = expected(get(API + "studies/" + hit.accession), row, today);
    for (const [name, value] of Object.entries(want)) {
      const same = MODEL.columns[name].many ? set(row[name]) === set(value) : row[name] === value;
      // The apostrophe keeps the value as text: no date or formula is made of it, and a typed column accepts it.
      if (!same) sheet.getRange(i + 1, at(name)).setValue(value && "'" + value);
    }
  }
}
