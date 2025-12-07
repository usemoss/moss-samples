/**
 * Conversation Indexing Sample
 * 
 * Creates a separate Moss index for each conversation JSON file.
 * 
 * Usage:
 *   npx tsx create-conversation-indexes.ts
 * 
 * Prerequisites:
 *   - Set MOSS_PROJECT_ID and MOSS_PROJECT_KEY in .env file
 *   - Conversation files in data/conversations/ directory
 */
import { MossClient, DocumentInfo } from "@inferedge/moss";
import { config } from 'dotenv';
import { readdir, readFile } from 'fs/promises';
import { join } from 'path';

config();

interface ConversationMessage {
  id: string;
  text: string;
  metadata: {
    conversation_id: string;
    message_number: string;
    total_messages: string;
    num_messages: string;
    topic: string;
  };
}

async function loadConversationFile(filePath: string, fileName: string): Promise<DocumentInfo[]> {
  const fileContent = await readFile(filePath, 'utf-8');
  const messages: ConversationMessage[] = JSON.parse(fileContent);
  
  return messages.map(msg => ({
    id: msg.id,
    text: msg.text,
    metadata: {
      ...msg.metadata,
      source_file: fileName
    }
  }));
}

async function createConversationIndexes(): Promise<void> {
  console.log('Conversation Indexing Sample');
  console.log('='.repeat(60));

  const projectId = process.env.MOSS_PROJECT_ID;
  const projectKey = process.env.MOSS_PROJECT_KEY;

  if (!projectId || !projectKey) {
    console.error('Missing MOSS_PROJECT_ID or MOSS_PROJECT_KEY');
    return;
  }

  const client = new MossClient(projectId, projectKey);
  const conversationsDir = join(__dirname, 'data', 'conversations');
  let successCount = 0;
  let failCount = 0;

  try {
    console.log('\nScanning files...');
    const files = await readdir(conversationsDir);
    const jsonFiles = files.filter(file => file.endsWith('.json'));
    console.log(`Found ${jsonFiles.length} files\n`);

    for (let i = 0; i < jsonFiles.length; i++) {
      const file = jsonFiles[i];
      
      try {
        console.log(`[${i + 1}/${jsonFiles.length}] ${file}...`);
        const documents = await loadConversationFile(join(conversationsDir, file), file);
        
        if (documents.length === 0) {
          console.log(`  Skipped`);
          failCount++;
          continue;
        }

        const indexName = file.replace('.json', '');
        await client.createIndex(indexName, documents, 'moss-minilm');
        
        console.log(`  Created '${indexName}' (${documents.length} messages)`);
        successCount++;
      } catch (error) {
        console.error(`  Failed: ${error}`);
        failCount++;
      }
    }

    console.log(`\n${'='.repeat(60)}`);
    console.log(`Created: ${successCount} | Failed: ${failCount}`);
    console.log('='.repeat(60));

  } catch (error) {
    console.error(`Error: ${error}`);
  }
}

export { createConversationIndexes, loadConversationFile };

if (require.main === module) {
  createConversationIndexes().catch(console.error);
}
