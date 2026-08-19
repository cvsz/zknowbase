export type DocumentRecord = {
  id: string; name: string; source_type: string; source_uri?: string | null;
  content_type?: string | null; status: string; chunk_count: number;
  size_bytes: number; created_at: string; updated_at: string; error?: string | null;
};

export type SourceCitation = {
  document_id: string; document_name: string; chunk_id: string; chunk_index: number;
  score: number; text: string; source_uri?: string | null;
};

export type QueryResponse = { answer: string; sources: SourceCitation[] };
export type PreviewResponse = { chunks: {index:number; text:string; characters:number}[]; total_chunks:number };
