import { ChangeEvent, DragEvent, FormEvent, ReactNode, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type IconName =
  | "grid"
  | "plus"
  | "folder"
  | "chat"
  | "document"
  | "activity"
  | "spark"
  | "help"
  | "settings"
  | "user"
  | "upload"
  | "send"
  | "check"
  | "chevron"
  | "search"
  | "shield"
  | "arrow";

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
    folder: <><path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H10l2 2h6.5A2.5 2.5 0 0 1 21 9.5v7A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5z" /></>,
    chat: <><path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H11l-4.5 3V17H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z" /></>,
    document: <><path d="M7 3h7l4 4v14H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" /><path d="M14 3v5h5M9 13h6M9 17h6" /></>,
    activity: <><path d="M4 17V7M9 20V4M14 16V8M19 19V5" /></>,
    spark: <><path d="m12 3 1.6 6.4L20 11l-6.4 1.6L12 19l-1.6-6.4L4 11l6.4-1.6z" /><path d="m19 3 .5 2.5L22 6l-2.5.5L19 9l-.5-2.5L16 6l2.5-.5z" /></>,
    help: <><circle cx="12" cy="12" r="9" /><path d="M9.8 9a2.3 2.3 0 1 1 3.8 1.7c-1 .7-1.6 1.1-1.6 2.5M12 16.5h.01" /></>,
    settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-1.7 1.7-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.1h-2.4v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L7 17l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.6-1H5.7v-2.4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L7 8.6l1.7-1.7.1.1a1.7 1.7 0 0 0 1.9.3 1.7 1.7 0 0 0 1-1.6v-.1h2.4v.1a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1 1.7 1.7-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.1V14h-.1a1.7 1.7 0 0 0-1.6 1z" /></>,
    user: <><circle cx="12" cy="8" r="3" /><path d="M5 20a7 7 0 0 1 14 0" /></>,
    upload: <><path d="M12 16V4M8 8l4-4 4 4M5 14v5h14v-5" /></>,
    send: <><path d="m21 3-7.5 18-3.2-7.3L3 10.5zM10.3 13.7 21 3" /></>,
    check: <><path d="m5 12 4 4L19 6" /></>,
    chevron: <><path d="m7 10 5 5 5-5" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.8" /><path d="m16 16 5 5" /></>,
    shield: <><path d="M12 3 20 6v5c0 5-3.3 8.5-8 10-4.7-1.5-8-5-8-10V6z" /><path d="m8.5 12 2.2 2.2 4.8-5" /></>,
    arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
  };
  return <svg aria-hidden="true" className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{paths[name]}</svg>;
}

function BrandMark() {
  return <div className="brand-mark" aria-hidden="true"><span className="brand-page"><span /></span><span className="brand-ring" /></div>;
}

const navItems: Array<[IconName, string]> = [["grid", "Overview"], ["folder", "Projects"], ["chat", "Conversations"], ["document", "Documents"], ["activity", "Activity"]];
const fileTree = {
  mandatory: [
    { key: "requirements", label: "Requirements / PRD" },
    { key: "architecture", label: "Architecture / Technical Design" },
    { key: "status", label: "Sprint / Project Status" },
    { key: "issues", label: "Issue / Bug Report" },
    { key: "rules", label: "Engineering / Release / Security Rules" },
  ],
  optional: [
    { key: "adrs", label: "ADRs" },
    { key: "meeting-notes", label: "Meeting Notes" },
    { key: "qa", label: "QA / Test Reports" },
    { key: "release-notes", label: "Release Notes" },
    { key: "changelogs", label: "Changelogs" },
    { key: "security-reviews", label: "Security Reviews" },
    { key: "deployment", label: "Deployment Reports" },
    { key: "api-docs", label: "API Documentation" },
    { key: "roadmaps", label: "Roadmaps" },
    { key: "retrospectives", label: "Retrospectives" },
  ],
} as const;
type UploadTarget = "mandatory" | "optional" | (typeof fileTree.mandatory[number]["key"] | typeof fileTree.optional[number]["key"]);

function App() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [activeNav, setActiveNav] = useState("Overview");
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState("Gemini 3.5 Flash");
  const [isReviewMode, setIsReviewMode] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [fileName, setFileName] = useState("");
  const [zoom, setZoom] = useState(100);
  const [uploadTarget, setUploadTarget] = useState<UploadTarget>("mandatory");
  const [uploadedFiles, setUploadedFiles] = useState<Record<string, string[]>>({});

  const acceptFiles = (files: FileList | null, target = uploadTarget) => {
    const file = files?.[0];
    if (file) {
      setFileName(file.name);
      setUploadedFiles((current) => ({ ...current, [target]: [...current[target], file.name] }));
    }
  };
  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    acceptFiles(event.dataTransfer.files);
  };
  const openFolderUpload = (target: UploadTarget) => {
    setUploadTarget(target);
    inputRef.current?.click();
  };
  const folderFileCount = (folder: "mandatory" | "optional") => [folder, ...fileTree[folder].map(({ key }) => key)].reduce((count, key) => count + (uploadedFiles[key]?.length ?? 0), 0);
  const submitMessage = (event: FormEvent) => {
    event.preventDefault();
    const trimmed = message.trim();
    if (!trimmed) return;
    setMessages((current) => [...current, trimmed]);
    setMessage("");
  };
  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => acceptFiles(event.target.files);

  return <div className="app-shell">
    <aside className="rail">
      <div className="rail-top"><BrandMark /><span className="rail-divider" /></div>
      <nav aria-label="Main navigation" className="rail-nav">
        {navItems.map(([icon, label]) => <button key={label} className={`rail-button ${activeNav === label ? "active" : ""}`} onClick={() => setActiveNav(label)} aria-label={label} title={label}><Icon name={icon} /></button>)}
      </nav>
      <div className="rail-bottom"><button className="rail-button" aria-label="AI insights"><Icon name="spark" /></button><button className="rail-button" aria-label="Help"><Icon name="help" /></button><button className="rail-button" aria-label="Settings"><Icon name="settings" /></button><button className="avatar" aria-label="Profile">NJ</button></div>
    </aside>

    <header className="topbar">
      <div className="wordmark"><BrandMark /><span>Project<span>Lens</span></span></div>
      <div className="project-context"><span className="status-dot" /> <span>Workspace / <strong>Atlas migration</strong></span><Icon name="chevron" size={14} /></div>
      <div className="top-actions"><button className="icon-button" aria-label="Search"><Icon name="search" /></button><button className="new-project"><Icon name="plus" size={16} /> New project</button><button className="user-chip"><span className="avatar tiny">NJ</span><span>Nitesh</span><Icon name="chevron" size={14} /></button></div>
    </header>

    <main className="workspace">
      <section className="left-pane">
        <div className="conversation-toolbar"><button className="conversation-title" onClick={() => setMessages([])}><span className="round-plus"><Icon name="plus" size={16} /></span> New conversation</button><button className="cross-session">Cross-session <Icon name="chevron" size={14} /></button></div>
        <div className="file-library">
          <div className="file-library-heading"><div><span className="small-label">PROJECT FILES</span><strong>Context library</strong></div><button className="library-add" aria-label="Upload a project file" onClick={() => openFolderUpload(uploadTarget)}><Icon name="plus" size={15} /></button></div>
          <div className="file-tree">
            <div className="file-folder mandatory-folder"><div className="folder-row"><Icon name="chevron" size={13} /><Icon name="folder" size={16} /><strong>Mandatory</strong><span className="folder-count">{folderFileCount("mandatory")}</span><button aria-label="Upload to Mandatory" onClick={() => openFolderUpload("mandatory")}><Icon name="plus" size={14} /></button></div><div className="folder-hint">Required to understand the project</div><div className="category-list">{fileTree.mandatory.map(({ key, label }) => <div className="category-with-files" key={key}><button className="category-row" onClick={() => openFolderUpload(key)}><Icon name="document" size={13} /><span>{label}</span><Icon name="plus" size={12} /></button>{(uploadedFiles[key] ?? []).map((name) => <div className="file-row" key={`${key}-${name}`}><Icon name="document" size={14} /><span>{name}</span></div>)}</div>)}</div>{(uploadedFiles.mandatory ?? []).map((name) => <div className="file-row" key={`mandatory-${name}`}><Icon name="document" size={14} /><span>{name}</span></div>)}</div>
            <div className="file-folder optional-folder"><div className="folder-row"><Icon name="chevron" size={13} /><Icon name="folder" size={16} /><strong>Optional</strong><span className="folder-count">{folderFileCount("optional")}</span><button aria-label="Upload to Optional" onClick={() => openFolderUpload("optional")}><Icon name="plus" size={14} /></button></div><div className="folder-hint">Useful supporting context</div><div className="category-list optional-list">{fileTree.optional.map(({ key, label }) => <div className="category-with-files" key={key}><button className="category-row" onClick={() => openFolderUpload(key)}><Icon name="document" size={13} /><span>{label}</span><Icon name="plus" size={12} /></button>{(uploadedFiles[key] ?? []).map((name) => <div className="file-row" key={`${key}-${name}`}><Icon name="document" size={14} /><span>{name}</span></div>)}</div>)}</div>{(uploadedFiles.optional ?? []).map((name) => <div className="file-row" key={`optional-${name}`}><Icon name="document" size={14} /><span>{name}</span></div>)}</div>
          </div>
          <p className="file-format-note">PDF · DOCX · MD · TXT · RTF · HTML · ZIP</p>
        </div>
        <div className="chat-scroll">
          <div className="welcome-card"><div className="eyebrow"><span className="eyebrow-dot" /> PROJECTLENS INTELLIGENCE</div><h1>See the whole project.</h1><p className="welcome-lead">Your context-aware document assistant for turning project knowledge into confident decisions.</p><div className="capability-list"><div><strong>Collect</strong><span>Bring PRDs, designs, issues, and release notes into one view.</span></div><div><strong>Connect</strong><span>Trace decisions, risks, and blockers across every source.</span></div><div><strong>Decide</strong><span>Ask grounded questions with citations and clear next steps.</span></div></div><div className="welcome-foot"><Icon name="shield" size={15} /> Rules-aware answers, always grounded in your workspace.</div></div>
          {messages.length > 0 && <div className="message-stack">{messages.map((item, index) => <div className="user-message" key={`${item}-${index}`}>{item}</div>)}<div className="assistant-message"><span className="mini-mark"><BrandMark /></span><div><strong>ProjectLens is ready.</strong><p>I’ll use your uploaded project context and document rules to work through that.</p></div></div></div>}
        </div>
        <form className="composer" onSubmit={submitMessage}><textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Ask about your project…" aria-label="Message ProjectLens" rows={3} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); submitMessage(event); } }} /><div className="composer-footer"><div className="composer-tools"><button type="button" className="attach-button" aria-label="Attach a document" onClick={() => inputRef.current?.click()}><Icon name="upload" size={17} /></button><input ref={inputRef} type="file" hidden accept=".pdf,.docx,.txt,.md,.rtf,.html,.zip" onChange={onFileChange} /><select value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)} aria-label="Select model"><option>Gemini 3.5 Flash</option><option>Ollama · GPT OSS 120B</option></select><button type="button" className={`review-toggle ${isReviewMode ? "on" : ""}`} onClick={() => setIsReviewMode((current) => !current)}><Icon name="shield" size={15} /> Review mode</button></div><button className="send-button" type="submit" aria-label="Send message"><Icon name="arrow" size={18} /></button></div></form>
      </section>

      <section className="document-pane">
        <div className="document-toolbar"><div className="toolbar-left"><span className="doc-type">PROJECT BRIEF</span><span className="toolbar-separator" /><span className="doc-title">Atlas migration plan</span><span className="saved-badge"><Icon name="check" size={13} /> Saved</span></div><div className="toolbar-right"><button className="toolbar-button"><Icon name="activity" size={16} /> Activity</button><button className="toolbar-button accent"><Icon name="upload" size={16} /> Upload</button><button className="toolbar-button filled">Export <Icon name="chevron" size={14} /></button></div></div>
        <div className="document-area"><div className="doc-summary"><div><span className="small-label">ACTIVE PROJECT</span><h2>Atlas migration</h2><p>One shared source of truth for delivery, risk, and release readiness.</p></div><div className="summary-metrics"><span><strong>12</strong> sources</span><span><strong>4</strong> open risks</span><span><strong>86%</strong> coverage</span></div></div><div className="document-canvas"><div className="canvas-header"><span>PROJECT CONTEXT</span><span className="canvas-date">Updated today · 09:42</span></div><h3>Let’s make your project legible.</h3><p className="canvas-intro">Upload the documents that hold your project together. ProjectLens will classify them, connect the context, and surface what needs your attention.</p><div className={`drop-zone ${isDragging ? "dragging" : ""}`} onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }} onDragLeave={() => setIsDragging(false)} onDrop={onDrop} onClick={() => inputRef.current?.click()} role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") inputRef.current?.click(); }}><div className="drop-icon"><Icon name="document" size={27} /></div><strong>{fileName || "Drop your first document here"}</strong><span>{fileName ? "Ready to add to your project context" : "or choose a file from your computer"}</span><button type="button" className="choose-file" onClick={(event) => { event.stopPropagation(); inputRef.current?.click(); }}><Icon name="upload" size={16} /> Choose file</button><small>PDF · DOCX · TXT · MD · RTF · HTML · ZIP <em>≤ 100 MB</em></small></div><div className="suggested-row"><div className="section-heading"><span className="small-label">START WITH</span><span>Recommended context</span></div><div className="suggested-cards"><div className="suggested-card"><span className="card-icon mint"><Icon name="document" size={17} /></span><span><strong>Requirements / PRD</strong><small>Define what good looks like</small></span><span className="priority">01</span></div><div className="suggested-card"><span className="card-icon coral"><Icon name="activity" size={17} /></span><span><strong>Architecture / Design</strong><small>Understand how it works</small></span><span className="priority">02</span></div><div className="suggested-card"><span className="card-icon gold"><Icon name="shield" size={17} /></span><span><strong>Release checklist</strong><small>Keep constraints visible</small></span><span className="priority">03</span></div></div></div></div></div><div className="zoom-controls"><button onClick={() => setZoom((value) => Math.max(70, value - 10))}>−</button><span>{zoom}%</span><button onClick={() => setZoom((value) => Math.min(130, value + 10))}>+</button></div></section>
    </main>
  </div>;
}

export default App;

createRoot(document.getElementById("root")!).render(<App />);
