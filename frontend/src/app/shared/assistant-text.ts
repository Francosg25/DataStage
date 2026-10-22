import { Component, computed, input } from "@angular/core";
import { NgTemplateOutlet } from "@angular/common";

interface Inline {
  type: "text" | "strong" | "code";
  text: string;
}
interface Block {
  type: "paragraph" | "heading" | "list" | "table" | "code";
  lines: string[];
  rows: string[][];
}

export function inlineText(text: string): Inline[] {
  return text
    .split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g)
    .filter(Boolean)
    .map((part) =>
      part.startsWith("**") && part.endsWith("**")
        ? { type: "strong", text: part.slice(2, -2) }
        : part.startsWith("`") && part.endsWith("`")
          ? { type: "code", text: part.slice(1, -1) }
          : { type: "text", text: part },
    );
}

export function assistantBlocks(text: string): Block[] {
  const lines = text.replace(/\r/g, "").split("\n");
  const blocks: Block[] = [];
  const cells = (line: string) =>
    line
      .trim()
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((cell) => cell.trim());
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index];
    if (!line.trim()) continue;
    if (line.trim().startsWith("```")) {
      const code: string[] = [];
      while (++index < lines.length && !lines[index].trim().startsWith("```"))
        code.push(lines[index]);
      blocks.push({ type: "code", lines: [code.join("\n")], rows: [] });
    } else if (/^#{1,6}\s/.test(line)) {
      blocks.push({
        type: "heading",
        lines: [line.replace(/^#{1,6}\s+/, "")],
        rows: [],
      });
    } else if (
      line.includes("|") &&
      index + 1 < lines.length &&
      /^\|?\s*:?-{3,}/.test(lines[index + 1].trim()) &&
      cells(lines[index + 1]).every((cell) => /^:?-{3,}:?$/.test(cell))
    ) {
      const rows = [cells(line)];
      index++;
      while (
        index + 1 < lines.length &&
        lines[index + 1].includes("|") &&
        lines[index + 1].trim()
      )
        rows.push(cells(lines[++index]));
      blocks.push({ type: "table", lines: [], rows });
    } else if (/^\s*(?:[-*]|\d+[.)])\s+/.test(line)) {
      const items = [line.replace(/^\s*(?:[-*]|\d+[.)])\s+/, "")];
      while (
        index + 1 < lines.length &&
        /^\s*(?:[-*]|\d+[.)])\s+/.test(lines[index + 1])
      )
        items.push(lines[++index].replace(/^\s*(?:[-*]|\d+[.)])\s+/, ""));
      blocks.push({ type: "list", lines: items, rows: [] });
    } else {
      const paragraph = [line];
      while (
        index + 1 < lines.length &&
        lines[index + 1].trim() &&
        !/^\s*(?:#|[-*] |\d+[.)] |```)/.test(lines[index + 1]) &&
        !lines[index + 1].includes("|")
      )
        paragraph.push(lines[++index]);
      blocks.push({
        type: "paragraph",
        lines: [paragraph.join("\n")],
        rows: [],
      });
    }
  }
  return blocks;
}

@Component({
  selector: "ds-assistant-text",
  template: `
    <ng-template #inline let-value>
      @for (part of parts(value); track $index) {
        @switch (part.type) {
          @case ("strong") {
            <strong>{{ part.text }}</strong>
          }
          @case ("code") {
            <code>{{ part.text }}</code>
          }
          @default {
            <span>{{ part.text }}</span>
          }
        }
      }
    </ng-template>
    @for (block of blocks(); track $index) {
      @switch (block.type) {
        @case ("heading") {
          <h3>
            <ng-container
              [ngTemplateOutlet]="inline"
              [ngTemplateOutletContext]="{ $implicit: block.lines[0] }"
            />
          </h3>
        }
        @case ("list") {
          <ul>
            @for (line of block.lines; track $index) {
              <li>
                <ng-container
                  [ngTemplateOutlet]="inline"
                  [ngTemplateOutletContext]="{ $implicit: line }"
                />
              </li>
            }
          </ul>
        }
        @case ("table") {
          <div class="answer-table">
            <table>
              <thead>
                <tr>
                  @for (cell of block.rows[0]; track $index) {
                    <th>
                      <ng-container
                        [ngTemplateOutlet]="inline"
                        [ngTemplateOutletContext]="{ $implicit: cell }"
                      />
                    </th>
                  }
                </tr>
              </thead>
              <tbody>
                @for (row of block.rows.slice(1); track $index) {
                  <tr>
                    @for (cell of row; track $index) {
                      <td>
                        <ng-container
                          [ngTemplateOutlet]="inline"
                          [ngTemplateOutletContext]="{ $implicit: cell }"
                        />
                      </td>
                    }
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
        @case ("code") {
          <pre><code>{{ block.lines[0] }}</code></pre>
        }
        @default {
          <p>
            <ng-container
              [ngTemplateOutlet]="inline"
              [ngTemplateOutletContext]="{ $implicit: block.lines[0] }"
            />
          </p>
        }
      }
    }
  `,
  imports: [NgTemplateOutlet],
  styles: `
    :host {
      display: block;
      font-size: 14px;
      line-height: 1.7;
      color: #29424e;
    }
    p {
      white-space: pre-wrap;
      margin: 8px 0;
    }
    h3 {
      font-size: 15px;
      margin: 16px 0 8px;
    }
    ul {
      padding-left: 22px;
    }
    li {
      margin: 5px 0;
    }
    code {
      background: #e3ebee;
      padding: 1px 5px;
      border-radius: 4px;
      font-size: 0.9em;
      overflow-wrap: anywhere;
    }
    pre {
      overflow: auto;
      padding: 14px;
      background: #e3ebee;
      border-radius: 8px;
    }
    pre code {
      padding: 0;
    }
    .answer-table {
      overflow-x: auto;
      margin: 14px 0;
    }
    table {
      border-collapse: collapse;
      min-width: 260px;
      width: 100%;
      font-size: 13px;
    }
    th,
    td {
      padding: 9px 12px;
      border: 1px solid #d7e2e5;
      text-align: left;
    }
    th {
      background: #e5efed;
      font-weight: 600;
    }
    tbody tr:nth-child(even) {
      background: #f6f9fa;
    }
  `,
})
export class AssistantText {
  text = input("");
  blocks = computed(() => assistantBlocks(this.text()));
  parts = inlineText;
}
