export interface Item {
  id: string;
  description: string;
}

export interface Group {
  id: string;
  members: string[]; // Array of item IDs
  description: string;
} 