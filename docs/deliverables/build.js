const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle, PageBreak,
  LevelFormat, Footer, PageNumber,
} = require("docx");

const W = 9026;                       // A4 content width in DXA
const ACCENT = "1F4E5F";
const HEADFILL = "1F4E5F";
const ZEBRA = "F2F5F7";

const P = (text, opts = {}) => new Paragraph({
  spacing: { after: opts.after ?? 140, line: 280 },
  ...opts.para,
  children: [new TextRun({ text, size: 21, ...opts.run })],
});

const H1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  spacing: { before: 320, after: 160 },
  children: [new TextRun({ text, bold: true, size: 30, color: ACCENT })],
});

const H2 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  spacing: { before: 260, after: 120 },
  children: [new TextRun({ text, bold: true, size: 24, color: "243742" })],
});

const H3 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_3,
  spacing: { before: 200, after: 100 },
  children: [new TextRun({ text, bold: true, size: 21, color: "4A5862" })],
});

const BULLET = (text) => new Paragraph({
  numbering: { reference: "bullets", level: 0 },
  spacing: { after: 70, line: 280 },
  children: [new TextRun({ text, size: 21 })],
});

const NUM = (text) => new Paragraph({
  numbering: { reference: "steps", level: 0 },
  spacing: { after: 70, line: 280 },
  children: [new TextRun({ text, size: 21 })],
});

const CHECK = (text) => new Paragraph({
  spacing: { after: 60, line: 280 },
  indent: { left: 200 },
  children: [new TextRun({ text: "☐   " + text, size: 21 })],
});

const cell = (text, { bold = false, header = false, fill = null, width } = {}) =>
  new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: header
      ? { type: ShadingType.CLEAR, fill: HEADFILL, color: "auto" }
      : fill
      ? { type: ShadingType.CLEAR, fill, color: "auto" }
      : undefined,
    margins: { top: 70, bottom: 70, left: 110, right: 110 },
    children: String(text).split("\n").map((line) => new Paragraph({
      spacing: { after: 0, line: 260 },
      children: [new TextRun({
        text: line, size: 19, bold: bold || header,
        color: header ? "FFFFFF" : "202A32",
      })],
    })),
  });

/** headers: string[]; rows: string[][]; weights: relative column widths */
const TABLE = (headers, rows, weights) => {
  const total = weights.reduce((a, b) => a + b, 0);
  const widths = weights.map((w) => Math.round((w / total) * W));
  widths[widths.length - 1] = W - widths.slice(0, -1).reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: W, type: WidthType.DXA },
    columnWidths: widths,
    borders: {
      top:    { style: BorderStyle.SINGLE, size: 2, color: "C9D3DA" },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: "C9D3DA" },
      left:   { style: BorderStyle.SINGLE, size: 2, color: "C9D3DA" },
      right:  { style: BorderStyle.SINGLE, size: 2, color: "C9D3DA" },
      insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "DCE3E8" },
      insideVertical:   { style: BorderStyle.SINGLE, size: 2, color: "DCE3E8" },
    },
    rows: [
      new TableRow({
        tableHeader: true,
        children: headers.map((h, i) => cell(h, { header: true, width: widths[i] })),
      }),
      ...rows.map((r, ri) => new TableRow({
        children: r.map((c, i) =>
          cell(c, { width: widths[i], fill: ri % 2 === 1 ? ZEBRA : null })),
      })),
    ],
  });
};

const SPACER = () => new Paragraph({ spacing: { after: 160 }, children: [] });

module.exports = { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  PageBreak, Footer, PageNumber, P, H1, H2, H3, BULLET, NUM, CHECK, TABLE, SPACER, W, ACCENT };
