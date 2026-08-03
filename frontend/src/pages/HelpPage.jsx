const SECTIONS = [
  {
    title: "How do I add a new document?",
    body: "Go to Upload. You need TWO files for one document: Part 1 is the header page (consignee and consignor details), Part 2 is the page with the item table. Choose both files, then press Upload. Processing takes about half a minute to a minute.",
  },
  {
    title: "Why do some fields say 'Not extracted'?",
    body: "The system only fills in a value when it is confident about it. If a field could not be read clearly from the photo, it is left blank on purpose instead of guessing wrong. You can type the correct value in yourself and it will be saved.",
  },
  {
    title: "What does the small percentage next to a field mean?",
    body: "That is how confident the system is about that value. Green/high numbers mean it is very likely correct. Yellow or red/low numbers mean you should double-check that value against the original photo.",
  },
  {
    title: "What does the sparkle icon mean?",
    body: "It means the system noticed a likely scanning mistake (like an 'I' read as a '1') and automatically fixed it. You can still change it if it's wrong.",
  },
  {
    title: "How do I fix a wrong value?",
    body: "Click into the field, type the correct value, then press Save (or press Enter). This replaces the old value completely - it does not keep the old one anywhere.",
  },
  {
    title: "What does Reprocess do?",
    body: "It runs the whole extraction again on the original photos and replaces all current values with fresh ones - including any corrections you made by hand. Only use this if you want to start over.",
  },
  {
    title: "What is the difference between Delete and File Delete?",
    body: "Delete permanently removes the document and its files entirely. File Delete only removes the original photos to save storage space, but keeps all the extracted information intact - you can still see and edit the data afterward, you just can't re-download the original photos or reprocess.",
  },
];

export default function HelpPage() {
  return (
    <div className="max-w-2xl">
      <h1 className="text-xl font-semibold mb-1">Help</h1>
      <p className="text-sm text-text-muted mb-6">Plain-language answers to common questions.</p>

      <div className="space-y-4">
        {SECTIONS.map((s) => (
          <div key={s.title} className="bg-surface border border-border rounded-lg p-4">
            <h2 className="text-sm font-semibold mb-1.5">{s.title}</h2>
            <p className="text-sm text-text-muted leading-relaxed">{s.body}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
