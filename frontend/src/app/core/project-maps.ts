export interface ProjectMap {
  id: string;
  slide: number;
  es: string;
  en: string;
  width: number;
  height: number;
  text: string[];
}

export interface ProjectMapCatalog {
  title: string;
  sourceFile: string;
  sourceSha256: string;
  date: string;
  location: string;
  pages: ProjectMap[];
}
