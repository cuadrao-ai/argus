"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getBusinessProfile, saveBusinessProfile, appearanceCommand, publishBusinessAppearance, type BusinessProfile, type BusinessProfilePatch } from "@/lib/business-profile-api";
import type { IdentityAppearance } from "@/lib/identity-appearance";
import {referenceCode} from "@/lib/failure-screen";

export function useBusinessProfile(id: string, enabled: boolean, onAccepted: () => void) {
  const [profile,setProfile] = useState<BusinessProfile|null>(null);
  const [failed,setFailed] = useState(false);
  const [refused,setRefused] = useState(false);
  const [reference,setReference]=useState<string|null>(null);
  const [attempt,setAttempt] = useState(0);
  const current = useRef<BusinessProfile|null>(null);
  const live = useRef(true);
  const imageRequest=useRef<AbortController|null>(null);
  const command = useRef<{ input: string; patch: BusinessProfilePatch; key: string }|null>(null);
  const imageCommand = useRef<{ input: string; run: ReturnType<typeof appearanceCommand> }|null>(null);
  const accept = useCallback((next: BusinessProfile) => {
    if (!live.current) return;
    current.current=next;setProfile(next);setFailed(false);
    imageRequest.current?.abort();imageRequest.current=new AbortController();
    void publishBusinessAppearance(next,imageRequest.current.signal).catch(()=>{});
  },[]);
  useEffect(()=>{
    live.current=true;
    const controller=new AbortController();
    if(enabled) getBusinessProfile(id,controller.signal).then(accept,error=>{if(!controller.signal.aborted){setFailed(true);setReference(referenceCode(error));setRefused(error?.status===403||error?.status===404);}});
    return()=>{live.current=false;controller.abort();imageRequest.current?.abort();};
  },[id,enabled,attempt,accept]);
  const failure = async (error: unknown): Promise<never> => {
    if (!live.current) throw error;
    const status = error && typeof error === "object" && "status" in error ? error.status : null;
    if(status===403||status===404)setRefused(true);
    if(status===409){command.current=null;imageCommand.current=null;try{accept(await getBusinessProfile(id));}catch{setFailed(true);}}
    throw error;
  };
  const save = async (patch: Omit<BusinessProfilePatch,"expected_revision">) => {
    if(!current.current||refused)throw new Error("Business profile unavailable");
    const input=JSON.stringify(patch);
    if(command.current?.input!==input) command.current={input,patch:{...patch,expected_revision:current.current.revision},key:crypto.randomUUID()};
    try {const next=await saveBusinessProfile(id,command.current.patch,command.current.key);accept(next);command.current=null;onAccepted();return next;}
    catch(error){return failure(error);}
  };
  const saveAppearance = async (value: IdentityAppearance) => {
    if(!current.current||refused)throw new Error("Business profile unavailable");
    const input=JSON.stringify(value);
    if(imageCommand.current?.input!==input)imageCommand.current={input,run:appearanceCommand(id,value,current.current)};
    try{const next=await imageCommand.current.run();accept(next);imageCommand.current=null;onAccepted();}
    catch(error){await failure(error);}
  };
  const retry=useCallback(()=>setAttempt(value=>value+1),[]);
  return { profile,failed,refused,reference,save,saveAppearance,retry };
}
